"""Start and inspect mystery-shopper runs.

Every run belongs to the browser that started it (see owner.py). A browser can read its own runs and the
shared examples (runs with no owner, made by the CLI or the seed command), and nothing else: someone else's
run id answers 404, exactly like a run that doesn't exist.
"""

import asyncio
import logging
import re
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from . import db
from .agent.compare import CompareError, compare_runs, previous_run
from .agent.explain import explain_run
from .agent.llm import LLMConfigError, groq_configured, make_llm
from .agent.recorder import list_runs, load_run
from .agent.service import RunConfigError, RunRequest, ServerInfo, execute, prepare, resolve_target
from .agent.site import allow_private_hosts
from .devsummary import developer_summary
from .ratelimit import rate_limit

router = APIRouter(prefix="/api/runs", tags=["runs"])
log = logging.getLogger(__name__)

FILE_NAME_RE = re.compile(r"^[\w.-]+\.png$")


class StartRun(BaseModel):
    store_url: str | None = Field(default=None, max_length=2048)  # None = the demo store; others are browse-only
    # Developer options. A deployed server refuses them (Settings.dev_options) and picks them itself.
    llm: Literal["mock", "groq", "scripted"] | None = None
    cassette: str | None = Field(default=None, max_length=100)
    record: str | None = Field(default=None, max_length=100)
    flaws: str | None = Field(default=None, max_length=500)  # demo store: on | off | all | keep | a,b,c
    checkout: bool | None = None  # demo store only
    paypal: Literal["mock", "sandbox"] | None = None
    browser: Literal["local", "kernel"] | None = None
    max_steps: int | None = Field(default=None, ge=1, le=60)


def _error(status: int, code: str, message: str) -> HTTPException:
    return HTTPException(status_code=status, detail={"error": code, "message": message})


NOT_FOUND = "We couldn't find that check."


def _readable(request: Request, run_id: int) -> dict[str, Any]:
    """The run, if this browser may see it. Someone else's run looks exactly like a missing one."""
    run = load_run(request.app.state.settings.database_path, run_id)
    if run is None or (run["owner_hash"] is not None and run["owner_hash"] != request.state.owner):
        raise _error(404, "UNKNOWN_RUN", NOT_FOUND)
    return run


def _public(run: dict[str, Any], viewer: str) -> dict[str, Any]:
    owner = run.pop("owner_hash")
    return {**run, "mine": owner == viewer, "example": owner is None}


@router.post("", status_code=202)
async def start_run(body: StartRun, request: Request):
    state = request.app.state
    settings = state.settings
    rate_limit(request, "run_limiter")
    chosen = body.model_fields_set - {"store_url"}
    if chosen and not settings.dev_options:
        raise _error(400, "RUN_CONFIG", f"Only store_url can be set on this server (not {', '.join(sorted(chosen))}).")
    demo = not body.store_url
    req = RunRequest(
        store_url=body.store_url,
        llm=body.llm or ("groq" if groq_configured() else "scripted"),
        cassette=body.cassette,
        record=body.record,
        flaws=body.flaws or "keep",
        checkout=demo if body.checkout is None else body.checkout,
        paypal=body.paypal or ("mock" if settings.paypal_mode == "mock" else "sandbox"),
        browser=body.browser,
        max_steps=body.max_steps or 25,
    )
    server = ServerInfo(settings.paypal_mode, state.paypal is not None)
    try:
        target = await resolve_target(req, settings.app_base_url)  # friendly errors for links we can't check
        live = not target.demo
        prepare(req, target.url, settings.database_path, server, live=live)  # fail fast, before any run row
    except RunConfigError as exc:
        raise _error(400, "RUN_CONFIG", str(exc)) from exc
    if state.run_lock.locked():
        raise _error(409, "RUN_IN_PROGRESS", "A check is already running. Try again when it finishes.")
    db.purge_old_runs(settings.database_path, settings.runs_dir, settings.retention_days)  # also on long uptimes

    started: asyncio.Future[int] = asyncio.get_running_loop().create_future()
    owner = request.state.owner

    async def worker():
        async with state.run_lock:
            try:
                await execute(req, target.url, settings.database_path, on_start=started.set_result, server=server,
                              live=live, allow_private=allow_private_hosts(settings.app_base_url),
                              owner_hash=owner, runs_dir=settings.runs_dir)
            except Exception as exc:
                if not started.done():
                    started.set_exception(exc)

    task = asyncio.create_task(worker())
    state.run_tasks.add(task)
    task.add_done_callback(state.run_tasks.discard)
    try:
        run_id = await asyncio.wait_for(started, timeout=30)
    except Exception as exc:
        log.exception("Run failed to start")
        raise _error(500, "RUN_START_FAILED", "The check couldn't start. Please try again.") from exc
    return {"run_id": run_id, "status": "running", "live": live}


@router.get("")
def get_runs(request: Request):
    return list_runs(request.app.state.settings.database_path, visible_to=request.state.owner)


def _compare(request: Request, before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    try:
        return compare_runs(request.app.state.settings.database_path, before["id"], after["id"])
    except CompareError as exc:
        raise _error(404, "COMPARE", "Both checks need to be finished before they can be compared.") from exc


@router.get("/compare")
def compare(request: Request, before: int, after: int):
    """Two checks you can see, of the same store, by the same browser."""
    b, a = _readable(request, before), _readable(request, after)
    if b["owner_hash"] != a["owner_hash"] or b["store_url"] != a["store_url"]:
        raise _error(400, "COMPARE", "Before and after only compares two checks of the same store.")
    return _compare(request, b, a)


@router.get("/{run_id}/compare")
def compare_with_previous(run_id: int, request: Request):
    """This check against the previous check of the same store by the same browser."""
    after = _readable(request, run_id)
    before_id = previous_run(request.app.state.settings.database_path, run_id)
    if before_id is None:
        raise _error(404, "NO_EARLIER_CHECK", "Make your fixes, then check again to see before and after.")
    return _compare(request, _readable(request, before_id), after)


class ExplainBody(BaseModel):
    llm: Literal["mock", "groq"] = "groq"
    cassette: str | None = Field(default=None, max_length=100)


@router.post("/{run_id}/explain")
async def explain(run_id: int, body: ExplainBody, request: Request):
    """LLM rephrasing of the run's deterministic fixes. Never changes the score."""
    _readable(request, run_id)
    rate_limit(request, "api_limiter")
    if body.model_fields_set and not request.app.state.settings.dev_options:
        raise _error(400, "RUN_CONFIG", "Only the default explanation can be requested on this server.")
    try:
        llm = make_llm(body.llm, body.cassette)
    except LLMConfigError as exc:
        raise _error(400, "RUN_CONFIG", str(exc)) from exc
    try:
        return await explain_run(request.app.state.settings.database_path, run_id, llm)
    except LookupError as exc:
        raise _error(404, "UNKNOWN_RUN", NOT_FOUND) from exc


@router.get("/{run_id}/developer-summary")
def get_developer_summary(run_id: int, request: Request):
    """'Send to my developer': failures, evidence, selectors and suggested code, as Markdown."""
    return {"run_id": run_id, "markdown": developer_summary(_readable(request, run_id))}


@router.get("/{run_id}/files/{name}")
def get_run_file(run_id: int, name: str, request: Request):
    """A screenshot from this run's folder, and nothing outside it."""
    _readable(request, run_id)
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
    return FileResponse(path, media_type="image/png", headers={"Cache-Control": "private, max-age=3600"})


@router.delete("/{run_id}", status_code=204)
def delete_run(run_id: int, request: Request):
    """Delete one of your checks: its results and screenshots. Shared examples can't be deleted."""
    run = _readable(request, run_id)
    if run["owner_hash"] is None:
        raise _error(403, "EXAMPLE", "Example checks are shared and can't be deleted.")
    if run["status"] in ("running", "awaiting_human"):
        raise _error(409, "RUN_IN_PROGRESS", "This check is still running. Delete it when it finishes.")
    settings = request.app.state.settings
    db.delete_run(settings.database_path, run_id, settings.runs_dir)
    return Response(status_code=204)


@router.get("/{run_id}")
def get_run(run_id: int, request: Request):
    return _public(_readable(request, run_id), request.state.owner)
