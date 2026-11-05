"""Builds a run from a request: validates config up front, sets store flaws, then runs the agent."""

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Literal

import httpx

from store.flaws import FLAW_KEYS

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


async def apply_flaws(store_url: str, mode: FlawMode) -> dict[str, bool]:
    url = store_url.rstrip("/") + "/admin/flaws.json"
    async with httpx.AsyncClient(timeout=10.0) as http:
        if mode != "keep":
            resp = await http.put(url, json={"flaws": {k: mode == "on" for k in FLAW_KEYS}})
        else:
            resp = await http.get(url)
        resp.raise_for_status()
        return resp.json()


@dataclass(frozen=True)
class ServerInfo:
    """What the store's server reports about PayPal. None in prepare() means: ask its /api/health."""

    paypal_mode: str
    paypal_configured: bool


def build_payment(req: RunRequest, store_url: str, server: ServerInfo | None = None) -> PaymentHandler | None:
    if not req.checkout:
        return None
    from .paypal_flow import PaymentConfigError, make_payment_handler

    try:
        return make_payment_handler(req.paypal, store_url, server.paypal_mode if server else None,
                                    server.paypal_configured if server else None)
    except PaymentConfigError as exc:
        raise RunConfigError(str(exc)) from exc


def prepare(req: RunRequest, store_url: str, db_path: Path, server: ServerInfo | None = None):
    """Validate everything that can fail before a run row exists. Raises RunConfigError."""
    try:
        if req.record and not req.record.replace("_", "").replace("-", "").isalnum():
            raise LLMConfigError(f"Invalid cassette name {req.record!r}")
        record_to = CASSETTE_DIR / f"{req.record}.json" if req.record else None
        llm = make_llm(req.llm, req.cassette, record_to)
    except LLMConfigError as exc:
        raise RunConfigError(str(exc)) from exc
    payment = build_payment(req, store_url, server)
    return llm, payment


async def execute(
    req: RunRequest,
    store_url: str,
    db_path: Path,
    on_start: Callable[[int], None] | None = None,
    server: ServerInfo | None = None,
) -> int:
    llm, payment = prepare(req, store_url, db_path, server)
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
    )
    try:
        return await run_shopper(cfg, llm, payment, on_start=on_start)
    finally:
        close = getattr(llm, "aclose", None)
        if close:
            await close()
