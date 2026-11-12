"""Builds a WebMCP run from a RunRequest (the browser path's twin in agent/service.py)."""

from dataclasses import replace
from pathlib import Path
from typing import Callable
from urllib.parse import urlparse

from ..agent.browser import BrowserConfigError, resolve_provider
from ..agent.llm import CASSETTE_DIR, LLMConfigError, close_llm, make_llm
from ..agent.paypal_flow import LIVE_TIMEOUTS, PayPalCheckout, PaymentConfigError, make_payment_handler
from ..agent.service import RunConfigError, RunRequest, ServerInfo, apply_flaws, flaw_selection
from ..config import sandbox_buyer
from .navigator import ScriptedWebMCP
from .shopper import WebMCPConfig, run_webmcp_shopper

SHOWCASE_TARGET = "gift card"
MAX_STEPS = 12
DEFAULT_CASSETTE = "webmcp_demo"


def prepare_webmcp(req: RunRequest, store_url: str, server: ServerInfo | None = None,
                   on_awaiting_human: Callable | None = None):
    """Validate everything that can fail before a run row exists. Raises RunConfigError. Returns (llm, buyer)."""
    external = req.store == "paypal_showcase"
    if external and req.paypal != "sandbox":
        raise RunConfigError("PayPal's WebMCP showcase only runs against the PayPal sandbox.")
    if external and req.llm == "mock":
        raise RunConfigError("Replayed runs only fit the demo store. Use the live agent or the scripted navigator.")
    if external and req.flaws != "keep":
        raise RunConfigError("Store flaws only exist on the GhostShopper demo store.")
    flaw_selection(req.flaws)
    try:
        resolve_provider(req.browser)
    except BrowserConfigError as exc:
        raise RunConfigError(str(exc)) from exc
    payment = _buyer(req, store_url, server, external, on_awaiting_human)
    try:
        if req.llm == "scripted":
            llm = ScriptedWebMCP(req.target_product)
        else:
            llm = make_llm(req.llm, req.cassette or (DEFAULT_CASSETTE if req.llm == "mock" else None),
                           None if not req.record else _cassette_path(req.record))
    except LLMConfigError as exc:
        raise RunConfigError(str(exc)) from exc
    return llm, payment


def _cassette_path(name: str) -> Path:
    if not name.replace("_", "").replace("-", "").isalnum():
        raise RunConfigError(f"Invalid cassette name {name!r}")
    return CASSETTE_DIR / f"{name}.json"


def _buyer(req: RunRequest, store_url: str, server: ServerInfo | None, external: bool,
           on_awaiting_human: Callable | None) -> PayPalCheckout:
    """The sandbox buyer who approves PayPal's window. On PayPal's showcase it is built here: the showcase has no
    GhostShopper server to ask, and only the sandbox buyer's login is needed."""
    if external:
        buyer = sandbox_buyer()
        if buyer is None:
            raise RunConfigError("Live sandbox checkout disabled; missing SANDBOX_BUYER_EMAIL / SANDBOX_BUYER_PASSWORD.")
        timeouts = LIVE_TIMEOUTS if req.human_wait else replace(LIVE_TIMEOUTS, human_s=0)
        parsed = urlparse(store_url)
        return PayPalCheckout(buyer, f"{parsed.scheme}://{parsed.netloc}", timeouts, "sandbox", on_awaiting_human,
                              internal_key="")  # PayPal's showcase must never get our key
    try:
        return make_payment_handler(req.paypal, store_url, server.paypal_mode if server else None,
                                    server.paypal_configured if server else None, on_awaiting_human, req.human_wait,
                                    internal_key=server.internal_key if server else None)
    except PaymentConfigError as exc:
        raise RunConfigError(str(exc)) from exc


async def execute_webmcp(req: RunRequest, store_url: str, db_path: Path, on_start: Callable[[int], None] | None,
                         server: ServerInfo | None, on_awaiting_human: Callable | None, owner_hash: str | None,
                         runs_dir: Path | None) -> int:
    llm, payment = prepare_webmcp(req, store_url, server, on_awaiting_human)
    external = req.store == "paypal_showcase"
    try:
        flaws = None if external else await apply_flaws(store_url, req.flaws)
        cfg = WebMCPConfig(
            store_url=store_url, db_path=db_path, target_product=req.target_product, external_demo=external,
            paypal_mode=req.paypal, flaws=flaws, max_steps=min(req.max_steps, MAX_STEPS), headless=req.headless,
            browser=req.browser, owner_hash=owner_hash, **({"runs_dir": runs_dir} if runs_dir else {}))
        return await run_webmcp_shopper(cfg, llm, payment, on_start=on_start)
    finally:
        await close_llm(llm)
