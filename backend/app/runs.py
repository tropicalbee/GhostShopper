"""Start and inspect mystery-shopper runs."""

import asyncio
from typing import Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from .agent.compare import CompareError, compare_runs, last_two_finished
from .agent.explain import explain_run
from .agent.llm import LLMConfigError, make_llm
from .agent.recorder import list_runs, load_run
from .agent.service import RunConfigError, RunRequest, ServerInfo, execute, prepare

router = APIRouter(prefix="/api/runs", tags=["runs"])


class StartRun(BaseModel):
    llm: Literal["mock", "groq"] = "groq"
    cassette: str | None = None
    record: str | None = None
    flaws: str = "keep"  # on | off | all | keep | comma-separated flaw keys
    checkout: bool = False
    paypal: Literal["mock", "sandbox"] = "sandbox"
    browser: Literal["local", "kernel"] | None = None
    max_steps: int = Field(default=25, ge=1, le=60)


@router.post("", status_code=202)
async def start_run(body: StartRun, request: Request):
    state = request.app.state
    settings = state.settings
    store_url = f"{settings.app_base_url}/store/"
    req = RunRequest(**body.model_dump())
    server = ServerInfo(settings.paypal_mode, state.paypal is not None)
    try:
        prepare(req, store_url, settings.database_path, server)  # fail fast on config, before any run row
    except RunConfigError as exc:
        raise HTTPException(status_code=400, detail={"error": "RUN_CONFIG", "message": str(exc)}) from exc
    if state.run_lock.locked():
        raise HTTPException(status_code=409, detail={"error": "RUN_IN_PROGRESS", "message": "One run at a time"})

    started: asyncio.Future[int] = asyncio.get_running_loop().create_future()

    async def worker():
        async with state.run_lock:
            try:
                await execute(req, store_url, settings.database_path, on_start=started.set_result, server=server)
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
    return {"run_id": run_id, "status": "running"}


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


@router.get("/{run_id}")
def get_run(run_id: int, request: Request):
    run = load_run(request.app.state.settings.database_path, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail={"error": "UNKNOWN_RUN", "message": "No such run"})
    return run
