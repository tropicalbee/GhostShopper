"""Start and inspect mystery-shopper runs.

Every run belongs to the browser that started it (see owner.py). A browser can read its own runs and the
shared examples (runs with no owner, made by the CLI or the seed command), and nothing else: someone else's
run id answers 404, exactly like a run that doesn't exist.
"""

import asyncio
import hmac
import json
import logging
import re
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Query, Request, Response
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from . import db
from .agent.compare import CompareError, compare_runs, previous_run, previous_run_with_other_flaws
from .agent.explain import explain_run
from .agent.llm import LLMConfigError, groq_configured, make_llm
from .agent.recorder import invalidate_run, list_runs, load_run
from .agent.service import RunConfigError, RunRequest, ServerInfo, execute, prepare, real_checkout_missing, resolve_target
from .agent.site import allow_private_hosts
from .devsummary import developer_summary
from .feed import feed_csv
from .ratelimit import rate_limit
from .trace import build_trace
from store import catalog
from store.app import ADMIN_COOKIE
from store.orders import StoreOrders

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
    headed: bool | None = None  # show the local browser window (the real sandbox login works headed)
    max_steps: int | None = Field(default=None, ge=1, le=60)
    # Open to everyone (not a developer option): a spending limit in USD, like "30.00". Only matters when the
    # shopper pays, which is on the demo store.
    budget: str | None = Field(default=None, max_length=20)
    # Pay with the real PayPal sandbox instead of the server's default. Needs the presenter unlock on a deployed
    # server (else 403 REAL_PAYMENT_LOCKED), plus sandbox keys and a Kernel browser (else 400 RUN_CONFIG). Demo store only.
    real_payment: bool | None = None


def _error(status: int, code: str, message: str) -> HTTPException:
    return HTTPException(status_code=status, detail={"error": code, "message": message})


def real_payment_allowed(request: Request) -> bool:
    """Real sandbox purchases need the presenter unlock (the /store/admin cookie); a dev server needs nothing."""
    settings = request.app.state.settings
    if settings.dev_options:
        return True
    token = settings.demo_admin_token
    supplied = request.cookies.get(ADMIN_COOKIE) or ""
    return bool(token) and hmac.compare_digest(supplied.encode(), token.encode())


NOT_FOUND = "We couldn't find that check."
START_TIMEOUT_S = 30  # how long a start may take (browser launch, first page) before the client gets an error


async def _aclose(*things: Any) -> None:
    """Close whatever of these holds a client. Used on objects built only to validate or after use."""
    for thing in things:
        close = getattr(thing, "aclose", None)
        if close:
            await close()


def _readable(request: Request, run_id: int) -> dict[str, Any]:
    """The run, if this browser may see it. Someone else's run looks exactly like a missing one."""
    run = load_run(request.app.state.settings.database_path, run_id)
    if run is None or (run["owner_hash"] is not None and run["owner_hash"] != request.state.owner):
        raise _error(404, "UNKNOWN_RUN", NOT_FOUND)
    return run


def _meta(request: Request, run_id: int) -> dict[str, Any]:
    """Owner and status of a run this browser may see, without building the whole payload. Same 404 rule as
    _readable; for endpoints that only need to know whose run it is."""
    with db.connect(request.app.state.settings.database_path) as conn:
        row = conn.execute("SELECT owner_hash, status FROM runs WHERE id = ?", (run_id,)).fetchone()
    if row is None or (row["owner_hash"] is not None and row["owner_hash"] != request.state.owner):
        raise _error(404, "UNKNOWN_RUN", NOT_FOUND)
    return dict(row)


def _public(run: dict[str, Any], viewer: str) -> dict[str, Any]:
    owner = run.pop("owner_hash")
    return {**run, "mine": owner == viewer, "example": owner is None}


@router.post("", status_code=202)
async def start_run(body: StartRun, request: Request):
    state = request.app.state
    settings = state.settings
    rate_limit(request, "run_limiter")
    chosen = body.model_fields_set - {"store_url", "budget", "real_payment"}
    if chosen and not settings.dev_options:
        raise _error(400, "RUN_CONFIG", f"Only store_url can be set on this server (not {', '.join(sorted(chosen))}).")
    demo = not body.store_url
    real = bool(body.real_payment)
    if real:
        if not real_payment_allowed(request):
            raise _error(403, "REAL_PAYMENT_LOCKED", "Real PayPal sandbox purchases need the presenter unlock. Unlock at /store/admin, or run without this option for the practice PayPal.")
        if not demo:
            raise _error(400, "RUN_CONFIG", "Real PayPal purchases only run on the GhostShopper demo store.")
        missing = real_checkout_missing(settings.paypal_configured or "sandbox" in state.paypal_clients)
        if missing:
            raise _error(400, "RUN_CONFIG", f"The real PayPal sandbox option isn't set up on this server. Missing: {', '.join(missing)}.")
    req = RunRequest(
        store_url=body.store_url,
        llm=body.llm or ("groq" if groq_configured() else "scripted"),
        cassette=body.cassette,
        record=body.record,
        flaws=body.flaws or "keep",
        checkout=True if real else (demo if body.checkout is None else body.checkout),
        paypal="sandbox" if real else (body.paypal or settings.paypal_mode),
        # A real purchase runs in a Kernel browser with headless off: its live view is how a person approves.
        browser="kernel" if real else body.browser,
        max_steps=body.max_steps or 25,
        budget=body.budget,
        headless=False if real else not body.headed,
    )
    # Both modes are served; the run is checked against the mode it asked for, not the server's default.
    server = ServerInfo(req.paypal, req.paypal in state.paypal_clients or settings.paypal_configured)
    try:
        target = await resolve_target(req, settings.app_base_url)  # friendly errors for links we can't check
        live = not target.demo
        # Fail fast, before any run row. execute() builds its own, so close what this one built.
        probe_llm, probe_payment = prepare(req, target.url, settings.database_path, server, live=live)
    except RunConfigError as exc:
        raise _error(400, "RUN_CONFIG", str(exc)) from exc
    await _aclose(probe_llm, probe_payment)
    # No await between the check and the acquire, so two near-simultaneous starts can't both pass.
    if state.run_lock.locked():
        raise _error(409, "RUN_IN_PROGRESS", "A check is already running. Try again when it finishes.")
    await state.run_lock.acquire()
    try:
        db.purge_old_runs(settings.database_path, settings.runs_dir, settings.retention_days)  # also on long uptimes
        started: asyncio.Future[int] = asyncio.get_running_loop().create_future()
        owner = request.state.owner

        async def worker():
            try:
                await execute(req, target.url, settings.database_path, on_start=started.set_result, server=server,
                              live=live, allow_private=allow_private_hosts(settings.app_base_url),
                              owner_hash=owner, runs_dir=settings.runs_dir)
            except Exception as exc:
                if not started.done():
                    started.set_exception(exc)

        # The store and the order endpoints use the run's PayPal mode while it runs, then go back to the default.
        if req.checkout:
            state.paypal_active = req.paypal
        task = asyncio.create_task(worker())

        def finished(_):
            state.paypal_active = settings.paypal_mode
            state.run_lock.release()

        # The lock is released when the task is done, however it ends (a task cancelled before it first runs
        # never enters its own try/finally, so the release can't live in the worker).
        task.add_done_callback(finished)
    except BaseException:
        state.paypal_active = settings.paypal_mode
        state.run_lock.release()
        raise
    state.run_tasks.add(task)
    task.add_done_callback(state.run_tasks.discard)
    try:
        run_id = await asyncio.wait_for(started, timeout=START_TIMEOUT_S)
    except Exception as exc:
        log.exception("Run failed to start")
        task.cancel()  # the client is told it failed, so no check may run behind its back
        raise _error(500, "RUN_START_FAILED", "The check couldn't start. Please try again.") from exc
    return {"run_id": run_id, "status": "running", "live": live}


@router.get("")
def get_runs(request: Request, limit: int = Query(50, ge=1, le=100), before: int | None = Query(None, ge=1)):
    """This browser's checks plus the shared examples, newest first. Page with `before` (the last id you have);
    fewer than `limit` items back means the end."""
    return list_runs(request.app.state.settings.database_path, limit=limit, visible_to=request.state.owner,
                     before=before)


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
def compare_with_previous(run_id: int, request: Request, before: int | None = Query(None, ge=1)):
    """This check against an earlier one of the same store by the same browser. Without `before`: the latest
    earlier check with different flaw settings, else the previous check. Nothing earlier answers 404."""
    after = _readable(request, run_id)
    if before is not None:
        b = _readable(request, before)
        if b["owner_hash"] != after["owner_hash"] or b["store_url"] != after["store_url"] or before >= run_id:
            raise _error(400, "COMPARE", "Before and after only compares an earlier check of the same store.")
        return _compare(request, b, after)
    path = request.app.state.settings.database_path
    before_id = previous_run_with_other_flaws(path, run_id) or previous_run(path, run_id)
    if before_id is None:
        raise _error(404, "NO_EARLIER_CHECK", "Make your fixes, then check again to see before and after.")
    return _compare(request, _readable(request, before_id), after)


class ExplainBody(BaseModel):
    llm: Literal["mock", "groq"] = "groq"
    cassette: str | None = Field(default=None, max_length=100)


@router.post("/{run_id}/explain")
async def explain(run_id: int, body: ExplainBody, request: Request):
    """LLM rephrasing of the run's deterministic fixes. Never changes the score."""
    if _meta(request, run_id)["owner_hash"] is None:
        raise _error(403, "EXAMPLE", "Example checks are shared and can't be changed.")
    rate_limit(request, "api_limiter")
    if body.model_fields_set and not request.app.state.settings.dev_options:
        raise _error(400, "RUN_CONFIG", "Only the default explanation can be requested on this server.")
    try:
        llm = make_llm(body.llm, body.cassette)
    except LLMConfigError as exc:
        raise _error(400, "RUN_CONFIG", str(exc)) from exc
    db_path = request.app.state.settings.database_path
    try:
        return await explain_run(db_path, run_id, llm)
    except LookupError as exc:
        raise _error(404, "UNKNOWN_RUN", NOT_FOUND) from exc
    finally:
        invalidate_run(db_path, run_id)  # explain rewrites checks.fix, which the cached payload carries
        await _aclose(llm)


@router.get("/{run_id}/developer-summary")
def get_developer_summary(run_id: int, request: Request):
    """'Send to my developer': failures, evidence, selectors and suggested code, as Markdown."""
    return {"run_id": run_id, "markdown": developer_summary(_readable(request, run_id))}


@router.get("/{run_id}/feed.csv")
def get_product_feed(run_id: int, request: Request):
    """The product feed row for PayPal's agent programs, built from what the shopper read. A file to download,
    never a submission: PayPal has no public sandbox API for Store Sync."""
    product_feed = _readable(request, run_id)["product_feed"]
    if product_feed is None:
        raise _error(409, "NO_PRODUCT_READ", "The shopper never reached a product page in this check, so there is nothing to put in a feed.")
    return Response(feed_csv(product_feed), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="ghostshopper-feed-check-{run_id}.csv"',
                             "Cache-Control": "private, no-store"})


@router.get("/{run_id}/files/{name}")
def get_run_file(run_id: int, name: str, request: Request):
    """A screenshot from this run's folder, and nothing outside it."""
    _meta(request, run_id)
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
    run = _meta(request, run_id)
    if run["owner_hash"] is None:
        raise _error(403, "EXAMPLE", "Example checks are shared and can't be deleted.")
    if run["status"] in ("running", "awaiting_human"):
        raise _error(409, "RUN_IN_PROGRESS", "This check is still running. Delete it when it finishes.")
    settings = request.app.state.settings
    db.delete_run(settings.database_path, run_id, settings.runs_dir)
    return Response(status_code=204)


def _purchase_trace(db_path: Path, run: dict[str, Any]) -> dict[str, Any]:
    """The run's purchase trace, from the store's orders and PayPal's stored records for this run."""
    store_orders = StoreOrders(db_path).for_run(run["id"])
    paypal = None
    if store_orders and store_orders[-1]["paypal_order_id"]:
        order_id = store_orders[-1]["paypal_order_id"]
        stored = db.get_order(db_path, order_id, include_raw=True) or {}
        paypal = {"id": order_id, "capture_error": stored.get("capture_error"),
                  "order": json.loads(stored["order_response"]) if stored.get("order_response") else None,
                  "capture": json.loads(stored["capture_response"]) if stored.get("capture_response") else None}
    product = catalog.get_by_name(run["target_product"]) if run["target_product"] else None
    return build_trace(run, product.sku if product else None, store_orders, paypal)


@router.get("/{run_id}")
def get_run(run_id: int, request: Request):
    run = _readable(request, run_id)
    run["trace"] = _purchase_trace(request.app.state.settings.database_path, run)
    return _public(run, request.state.owner)
