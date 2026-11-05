"""Builds a run from a request: validates config up front, sets store flaws, then runs the agent."""

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Literal

import httpx

from store.flaws import CLASSIC_FLAWS, FLAW_KEYS

from .browser import BrowserConfigError, resolve_provider
from .llm import CASSETTE_DIR, LLMConfigError, make_llm
from .loop import DEFAULT_TARGET, PaymentHandler, RunConfig, run_shopper

FlawMode = Literal["on", "off", "keep"]


class RunConfigError(ValueError):
    pass


@dataclass
class RunRequest:
    llm: Literal["mock", "groq"] = "groq"
    cassette: str | None = None  # mock: cassette to replay
    record: str | None = None  # groq: save the run as this cassette name
    flaws: FlawMode = "keep"
    checkout: bool = False
    paypal: Literal["mock", "sandbox"] = "sandbox"
    target_product: str = DEFAULT_TARGET
    max_steps: int = 25
    headless: bool = True
    browser: str | None = None  # local | kernel; None = BROWSER_PROVIDER (default local)


def flaw_selection(mode: str) -> dict[str, bool] | None:
    """on = the classic demo flaws, off = none, all = every flaw, keep = leave as is, or 'a,b,c'."""
    mode = (mode or "keep").strip()
    if mode == "keep":
        return None
    if mode == "off":
        return {k: False for k in FLAW_KEYS}
    if mode == "all":
        return {k: True for k in FLAW_KEYS}
    if mode == "on":
        return {k: k in CLASSIC_FLAWS for k in FLAW_KEYS}
    keys = {k.strip() for k in mode.split(",") if k.strip()}
    unknown = keys - set(FLAW_KEYS)
    if unknown:
        raise RunConfigError(f"Unknown flaw(s): {', '.join(sorted(unknown))}. Known: {', '.join(FLAW_KEYS)}")
    return {k: k in keys for k in FLAW_KEYS}


async def apply_flaws(store_url: str, mode: FlawMode | str) -> dict[str, bool]:
    url = store_url.rstrip("/") + "/admin/flaws.json"
    selection = flaw_selection(mode)
    async with httpx.AsyncClient(timeout=10.0) as http:
        if selection is not None:
            resp = await http.put(url, json={"flaws": selection})
        else:
            resp = await http.get(url)
        resp.raise_for_status()
        return resp.json()


@dataclass(frozen=True)
class ServerInfo:
    """What the store's server reports about PayPal. None in prepare() means: ask its /api/health."""

    paypal_mode: str
    paypal_configured: bool


def build_payment(req: RunRequest, store_url: str, server: ServerInfo | None = None,
                  on_awaiting_human: Callable | None = None) -> PaymentHandler | None:
    if not req.checkout:
        return None
    from .paypal_flow import PaymentConfigError, make_payment_handler

    try:
        return make_payment_handler(req.paypal, store_url, server.paypal_mode if server else None,
                                    server.paypal_configured if server else None, on_awaiting_human)
    except PaymentConfigError as exc:
        raise RunConfigError(str(exc)) from exc


def prepare(req: RunRequest, store_url: str, db_path: Path, server: ServerInfo | None = None,
            on_awaiting_human: Callable | None = None):
    """Validate everything that can fail before a run row exists. Raises RunConfigError."""
    flaw_selection(req.flaws)  # raises on unknown flaw keys
    try:
        resolve_provider(req.browser)
    except BrowserConfigError as exc:
        raise RunConfigError(str(exc)) from exc
    try:
        if req.record and not req.record.replace("_", "").replace("-", "").isalnum():
            raise LLMConfigError(f"Invalid cassette name {req.record!r}")
        record_to = CASSETTE_DIR / f"{req.record}.json" if req.record else None
        llm = make_llm(req.llm, req.cassette, record_to)
    except LLMConfigError as exc:
        raise RunConfigError(str(exc)) from exc
    payment = build_payment(req, store_url, server, on_awaiting_human)
    return llm, payment


async def execute(
    req: RunRequest,
    store_url: str,
    db_path: Path,
    on_start: Callable[[int], None] | None = None,
    server: ServerInfo | None = None,
    on_awaiting_human: Callable | None = None,
) -> int:
    llm, payment = prepare(req, store_url, db_path, server, on_awaiting_human)
    flaws = await apply_flaws(store_url, req.flaws)
    cfg = RunConfig(
        store_url=store_url,
        db_path=db_path,
        target_product=req.target_product,
        checkout=req.checkout,
        paypal_mode=req.paypal if req.checkout else "off",
        flaws=flaws,
        max_steps=req.max_steps,
        headless=req.headless,
        browser=req.browser,
    )
    try:
        return await run_shopper(cfg, llm, payment, on_start=on_start)
    finally:
        close = getattr(llm, "aclose", None)
        if close:
            await close()
