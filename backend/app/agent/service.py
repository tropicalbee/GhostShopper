"""Builds a run from a request: validates config up front, sets store flaws, then runs the agent."""

import os
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Callable, Literal

import httpx

from store.flaws import CLASSIC_FLAWS, FLAW_KEYS

from ..config import sandbox_buyer
from .browser import BrowserConfigError, resolve_provider
from .llm import CASSETTE_DIR, LLMConfigError, close_llm, make_llm
from .loop import DEFAULT_TARGET, PaymentHandler, RunConfig, run_shopper
from .site import SiteError, Target, preflight

FlawMode = Literal["on", "off", "keep"]


class RunConfigError(ValueError):
    pass


@dataclass
class RunRequest:
    llm: Literal["mock", "live", "scripted"] = "live"  # scripted = rule-based navigator, not an LLM
    cassette: str | None = None  # mock: cassette to replay
    store_url: str | None = None  # None = our demo store; anything else is a live store (browse-only)
    record: str | None = None  # live: save the run as this cassette name
    flaws: FlawMode = "keep"
    checkout: bool = False
    paypal: Literal["mock", "sandbox"] = "sandbox"
    payment: Literal["popup", "vault"] = "popup"  # vault: pay with the buyer's saved PayPal account, no popup
    target_product: str = DEFAULT_TARGET
    max_steps: int = 25
    headless: bool = True
    browser: str | None = None  # local | kernel; None = BROWSER_PROVIDER (default local)
    budget: str | None = None  # spending limit in USD, e.g. "30.00"; None = no limit. See parse_budget.
    human_wait: bool = True  # False: a PayPal human check fails the run at once (nobody can reach its browser)


MAX_BUDGET = Decimal("10000")


def parse_budget(value: str | None) -> Decimal | None:
    """A spending limit as a positive USD amount with at most two decimals. None or blank = no limit."""
    if value is None or not str(value).strip():
        return None
    text = str(value).strip().lstrip("$").strip()
    try:
        amount = Decimal(text)
    except InvalidOperation:
        raise RunConfigError(f"The spending limit must be an amount in US dollars, like 30.00 (not {value!r}).") from None
    if not amount.is_finite() or amount <= 0:
        raise RunConfigError("The spending limit must be more than 0.")
    if amount > MAX_BUDGET:  # before quantize, which overflows on huge exponents like 1E+30
        raise RunConfigError(f"The spending limit can be at most {MAX_BUDGET:.2f}.")
    try:
        rounded = amount.quantize(Decimal("0.01"))
    except ArithmeticError:  # InvalidOperation is a subclass
        raise RunConfigError(f"The spending limit must be an amount in US dollars, like 30.00 (not {value!r}).") from None
    if amount != rounded:
        raise RunConfigError("The spending limit can have at most two decimal places, like 30.00.")
    return rounded


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
    token = os.getenv("DEMO_ADMIN_TOKEN", "").strip()
    async with httpx.AsyncClient(timeout=10.0, headers={"X-Admin-Token": token} if token else {}) as http:
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


def real_checkout_missing(paypal_configured: bool) -> list[str]:
    """What a real PayPal sandbox purchase still needs on this server. The browser must be a Kernel one (headless
    off, so a person can open its live view when PayPal stops the agent), hence KERNEL_API_KEY. Empty = available."""
    missing = []
    if not paypal_configured:
        missing.append("PAYPAL_CLIENT_ID / PAYPAL_CLIENT_SECRET")
    if not os.getenv("KERNEL_API_KEY", "").strip():
        missing.append("KERNEL_API_KEY")
    if sandbox_buyer() is None:
        missing.append("SANDBOX_BUYER_EMAIL / SANDBOX_BUYER_PASSWORD")
    return missing


def build_payment(req: RunRequest, store_url: str, server: ServerInfo | None = None,
                  on_awaiting_human: Callable | None = None, db_path: Path | None = None) -> PaymentHandler | None:
    if not req.checkout:
        return None
    if req.payment == "vault":
        from .paypal_flow import PaymentConfigError
        from .vault_flow import make_vault_handler

        if db_path is None:
            raise RunConfigError("Vault payment needs the database path.")
        try:
            return make_vault_handler(req.paypal, store_url, db_path, server.paypal_mode if server else None,
                                      server.paypal_configured if server else None)
        except PaymentConfigError as exc:
            raise RunConfigError(str(exc)) from exc
    from .paypal_flow import PaymentConfigError, make_payment_handler

    try:
        return make_payment_handler(req.paypal, store_url, server.paypal_mode if server else None,
                                    server.paypal_configured if server else None, on_awaiting_human, req.human_wait)
    except PaymentConfigError as exc:
        raise RunConfigError(str(exc)) from exc


async def resolve_target(req: RunRequest, app_base_url: str) -> Target:
    """Which store this run visits. A pasted link gets a polite preflight with a friendly error."""
    if not req.store_url:
        return Target(f"{app_base_url}/store/", f"{app_base_url}", True)
    try:
        target = await preflight(req.store_url, app_base_url)
    except SiteError as exc:
        raise RunConfigError(str(exc)) from exc
    if not target.demo and req.checkout:
        raise RunConfigError("Purchases only run on the GhostShopper demo store. "
                             "Live stores are checked up to the PayPal button, without paying.")
    return target


def prepare(req: RunRequest, store_url: str, db_path: Path, server: ServerInfo | None = None,
            on_awaiting_human: Callable | None = None, live: bool = False):
    """Validate everything that can fail before a run row exists. Raises RunConfigError."""
    if live and req.checkout:
        raise RunConfigError("Purchases only run on the GhostShopper demo store.")
    if live and req.llm == "mock":
        raise RunConfigError("Replayed runs only fit the demo store. Use the live agent or the scripted navigator.")
    flaw_selection(req.flaws)  # raises on unknown flaw keys
    parse_budget(req.budget)
    try:
        resolve_provider(req.browser)
    except BrowserConfigError as exc:
        raise RunConfigError(str(exc)) from exc
    # The payment handler first: if it can't be built, no LLM client has been opened to leak.
    payment = build_payment(req, store_url, server, on_awaiting_human, db_path)
    try:
        if req.record and not req.record.replace("_", "").replace("-", "").isalnum():
            raise LLMConfigError(f"Invalid cassette name {req.record!r}")
        record_to = CASSETTE_DIR / f"{req.record}.json" if req.record else None
        if req.llm == "scripted":
            from ..eval.navigator import ScriptedNavigator

            llm = ScriptedNavigator(None if live else req.target_product)
        else:
            llm = make_llm(req.llm, req.cassette, record_to)
    except LLMConfigError as exc:
        raise RunConfigError(str(exc)) from exc
    return llm, payment


async def execute(
    req: RunRequest,
    store_url: str,
    db_path: Path,
    on_start: Callable[[int], None] | None = None,
    server: ServerInfo | None = None,
    on_awaiting_human: Callable | None = None,
    live: bool = False,
    allow_private: bool = True,
    owner_hash: str | None = None,
    runs_dir: Path | None = None,
) -> int:
    llm, payment = prepare(req, store_url, db_path, server, on_awaiting_human, live=live)
    flaws = None if live else await apply_flaws(store_url, req.flaws)
    cfg = RunConfig(
        store_url=store_url,
        db_path=db_path,
        target_product=None if live else req.target_product,
        live=live,
        allow_private=allow_private,
        checkout=req.checkout,
        paypal_mode=req.paypal if req.checkout else "off",
        flaws=flaws,
        max_steps=req.max_steps,
        headless=req.headless,
        browser=req.browser,
        owner_hash=owner_hash,
        budget=parse_budget(req.budget) if req.checkout else None,
        **({"runs_dir": runs_dir} if runs_dir else {}),
    )
    try:
        return await run_shopper(cfg, llm, payment, on_start=on_start)
    finally:
        await close_llm(llm)
