"""Start and inspect mystery-shopper runs."""

import asyncio
import re
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from . import db
from .agent.compare import CompareError, compare_runs, last_two_finished
from .agent.explain import explain_run
from .agent.llm import LLMConfigError, make_llm
from .agent.recorder import list_runs, load_run
from .agent.service import RunConfigError, RunRequest, ServerInfo, execute, prepare, resolve_target
from .agent.site import allow_private_hosts
from .devsummary import developer_summary

router = APIRouter(prefix="/api/runs", tags=["runs"])

FILE_NAME_RE = re.compile(r"^[\w.-]+\.png$")


class StartRun(BaseModel):
    store_url: str | None = None  # None = the GhostShopper demo store; any other link is browse-only
    llm: Literal["mock", "groq", "scripted"] = "groq"
    cassette: str | None = None
    record: str | None = None
    flaws: str = "keep"  # demo store only: on | off | all | keep | comma-separated flaw keys
    checkout: bool = False  # demo store only
    paypal: Literal["mock", "sandbox"] = "sandbox"
    browser: Literal["local", "kernel"] | None = None
    max_steps: int = Field(default=25, ge=1, le=60)


def _bad_request(message: str) -> HTTPException:
    return HTTPException(status_code=400, detail={"error": "RUN_CONFIG", "message": message})


@router.post("", status_code=202)
async def start_run(body: StartRun, request: Request):
    state = request.app.state
    settings = state.settings
    req = RunRequest(**body.model_dump())
    server = ServerInfo(settings.paypal_mode, state.paypal is not None)
    try:
        target = await resolve_target(req, settings.app_base_url)  # friendly errors for links we can't check
        live = not target.demo
        prepare(req, target.url, settings.database_path, server, live=live)  # fail fast, before any run row
    except RunConfigError as exc:
        raise _bad_request(str(exc)) from exc
    if state.run_lock.locked():
        raise HTTPException(status_code=409, detail={"error": "RUN_IN_PROGRESS",
                                                     "message": "A check is already running. Try again when it finishes."})

    started: asyncio.Future[int] = asyncio.get_running_loop().create_future()

    async def worker():
        async with state.run_lock:
            try:
                await execute(req, target.url, settings.database_path, on_start=started.set_result, server=server,
                              live=live, allow_private=allow_private_hosts(settings.app_base_url))
            except Exception as exc:
                if not started.done():
                    started.set_exception(exc)

    task = asyncio.create_task(worker())
    state.run_tasks.add(task)
    task.add_done_callback(state.run_tasks.discard)
    try:
        run_id = await asyncio.wait_for(started, timeout=30)
    except Exception as exc:
        raise HTTPException(status_code=500, detail={"error": "RUN_START_FAILED", "message": str(exc)[:300]}) from exc
    return {"run_id": run_id, "status": "running", "live": live}


@router.get("")
def get_runs(request: Request):
    return list_runs(request.app.state.settings.database_path)


@router.get("/compare")
def compare(request: Request, before: int | None = None, after: int | None = None):
    """Before/after: score change, failures fixed, failures remaining. Without ids: the last two finished runs."""
    db_path = request.app.state.settings.database_path
    try:
        if before is None or after is None:
            before, after = last_two_finished(db_path)
        return compare_runs(db_path, before, after)
    except CompareError as exc:
        raise HTTPException(status_code=404, detail={"error": "COMPARE", "message": str(exc)}) from exc


class ExplainBody(BaseModel):
    llm: Literal["mock", "groq"] = "groq"
    cassette: str | None = None


@router.post("/{run_id}/explain")
async def explain(run_id: int, body: ExplainBody, request: Request):
    """LLM rephrasing of the run's deterministic fixes. Never changes the score."""
    try:
        llm = make_llm(body.llm, body.cassette)
    except LLMConfigError as exc:
        raise HTTPException(status_code=400, detail={"error": "RUN_CONFIG", "message": str(exc)}) from exc
    try:
        return await explain_run(request.app.state.settings.database_path, run_id, llm)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail={"error": "UNKNOWN_RUN", "message": str(exc)}) from exc


@router.get("/{run_id}/developer-summary")
def get_developer_summary(run_id: int, request: Request):
    """'Send to my developer': failures, evidence, selectors and suggested code, as Markdown."""
    run = load_run(request.app.state.settings.database_path, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail={"error": "UNKNOWN_RUN", "message": "No such run"})
    return {"run_id": run_id, "markdown": developer_summary(run)}


@router.get("/{run_id}/files/{name}")
def get_run_file(run_id: int, name: str, request: Request):
    """A screenshot from this run's folder, and nothing outside it."""
    if not FILE_NAME_RE.match(name):
        raise HTTPException(status_code=404)
    with db.connect(request.app.state.settings.database_path) as conn:
        row = conn.execute("SELECT screenshot_path FROM steps WHERE run_id = ? AND screenshot_path IS NOT NULL LIMIT 1",
                           (run_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404)
    folder = Path(row["screenshot_path"]).parent.resolve()
    path = (folder / name).resolve()
    if path.parent != folder or not path.is_file():
        raise HTTPException(status_code=404)
    return FileResponse(path, media_type="image/png")


@router.get("/{run_id}")
def get_run(run_id: int, request: Request):
    run = load_run(request.app.state.settings.database_path, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail={"error": "UNKNOWN_RUN", "message": "No such run"})
    return run
