"""The mystery-shopper agent: a real tool-calling loop. The LLM chooses every action."""

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Protocol

from playwright.async_api import Error as PlaywrightError

from ..config import REPO_ROOT
from ..scoring import compute_score
from .browser import BrowserSession, PageTools, ToolError
from .engine import CheckEngine
from .llm import LLM
from .recorder import RunRecorder

DEFAULT_TARGET = "Speckled Stoneware Mug"
OBSERVATION_LIMIT = 4000


def _fn(name: str, description: str, properties: dict[str, Any] | None = None, required: list[str] | None = None):
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {"type": "object", "properties": properties or {}, "required": required or []},
        },
    }


BROWSE_TOOLS = [
    _fn("open_page", "Open a page on the store by absolute or relative URL.",
        {"url": {"type": "string"}}, ["url"]),
    _fn("find_elements", "List the clickable elements and form fields on the current page, each with an id.",
        {"kind": {"type": "string", "enum": ["all", "links", "buttons", "inputs"]}}),
    _fn("read_text", "Read the current page's title, main visible text and structured data. Images cannot be read."),
    _fn("click", "Click an element by the id from the latest find_elements call.",
        {"element_id": {"type": "string"}}, ["element_id"]),
    _fn("fill_form", "Fill form fields. For checkboxes use value 'true' or 'false'; for selects use the option text.",
        {"fields": {"type": "array", "items": {"type": "object", "properties": {
            "element_id": {"type": "string"}, "value": {"type": "string"}}, "required": ["element_id", "value"]}}},
        ["fields"]),
    _fn("take_screenshot", "Save a screenshot of the current page as evidence.", {"label": {"type": "string"}}),
    _fn("finish", "End the run and report what you found.",
        {"outcome": {"type": "string", "enum": ["reached_checkout", "purchased", "blocked", "gave_up"]},
         "summary": {"type": "string", "description": "What happened and anything that blocked or slowed you."},
         "price": {"type": "string", "description": "Price as read from the page, or 'unknown'."},
         "in_stock": {"type": "string", "description": "Stock status as read, or 'unknown'."}},
        ["outcome", "summary"]),
]
PAY_TOOL = _fn(
    "pay_with_paypal",
    "On the checkout page: click the PayPal button, sign in with the customer's saved PayPal account and "
    "approve the payment. Sign-in details are handled for you; never ask for them.",
)

SYSTEM_PROMPT = """You are an AI shopping agent acting for a customer. You browse a merchant's web store using tools only.
You cannot see images; you only know what the tools return.
Rules:
- Inspect before acting: use find_elements and read_text, then click or fill forms.
- Use element ids exactly as returned by the most recent find_elements call on the current page.
- Never invent a price or stock status. If it is not readable, report 'unknown'.
- If an action does not get you closer, try a reasonable alternative. Give up after a few failed attempts.
- Finish by calling finish with the outcome, the price and stock you read, and a short summary of anything that blocked or slowed you."""


def goal_text(target: str, store_url: str, checkout: bool) -> str:
    if checkout:
        return (f"Buy one '{target}' from the store at {store_url}. Find it, read its price and stock status, "
                f"go to checkout, pay with pay_with_paypal, and report the order number.")
    return (f"Find the product '{target}' in the store at {store_url}, read its price and stock status, "
            f"and get to the checkout page. Do not pay.")


class PaymentHandler(Protocol):
    secrets: tuple[str, ...]

    async def pay(self, tools: PageTools, recorder: RunRecorder, engine: CheckEngine) -> str: ...


@dataclass
class RunConfig:
    store_url: str
    db_path: Path
    target_product: str = DEFAULT_TARGET
    checkout: bool = False
    paypal_mode: str = "off"  # off | mock | sandbox
    flaws: dict[str, bool] | None = None
    max_steps: int = 25
    headless: bool = True
    runs_dir: Path = field(default_factory=lambda: REPO_ROOT / "runs")


async def run_shopper(
    cfg: RunConfig,
    llm: LLM,
    payment: PaymentHandler | None = None,
    on_start: Callable[[int], None] | None = None,
) -> int:
    if cfg.checkout and payment is None:
        raise ValueError("A checkout run needs a payment handler")
    rec = RunRecorder.start(
        cfg.db_path,
        store_url=cfg.store_url,
        goal=goal_text(cfg.target_product, cfg.store_url, cfg.checkout),
        target_product=cfg.target_product,
        checkout=cfg.checkout,
        paypal_mode=cfg.paypal_mode if cfg.checkout else "off",
        flaws=cfg.flaws,
        llm=llm.kind,
        model=llm.model,
        secrets=payment.secrets if payment else (),
    )
    if on_start:
        on_start(rec.run_id)
    shots_dir = cfg.runs_dir / f"run-{rec.run_id}"
    status, outcome, summary, report, error = "completed", "step_limit", None, None, None
    idx = 0
    engine: CheckEngine | None = None
    try:
        async with BrowserSession(headless=cfg.headless) as session:
            tools = PageTools(session, cfg.store_url, shots_dir)
            engine = CheckEngine(rec, cfg.target_product, tools)
            specs = BROWSE_TOOLS + ([PAY_TOOL] if cfg.checkout else [])
            messages: list[dict[str, Any]] = [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": goal_text(cfg.target_product, cfg.store_url, cfg.checkout)},
            ]
            nudges = 0
            done = False
            while not done and idx < cfg.max_steps:
                reply = await llm.complete(messages, specs)
                messages.append(reply.message)
                if not reply.tool_calls:
                    nudges += 1
                    if nudges > 2:
                        outcome, summary = "gave_up", reply.content
                        break
                    messages.append({"role": "user", "content": "Use one of the tools, or call finish."})
                    continue
                for call in reply.tool_calls:
                    started = time.monotonic()
                    ok = True
                    try:
                        obs = await _dispatch(call.name, call.arguments, tools, rec, engine, payment)
                    except (ToolError, PlaywrightError, KeyError, TypeError) as exc:
                        ok = False
                        msg = f"missing argument {exc}" if isinstance(exc, KeyError) else str(exc).splitlines()[0]
                        obs = f"Error: {msg[:300]}"
                    shot = None
                    try:
                        shot = await tools.screenshot(f"step-{idx:02d}")
                    except Exception:
                        pass
                    step_id = rec.add_step(
                        idx=idx, tool=call.name, args=call.arguments, thought=reply.content, observation=obs, ok=ok,
                        url=tools.page.url, screenshot_path=shot, duration_ms=int((time.monotonic() - started) * 1000),
                    )
                    idx += 1
                    if call.name not in ("finish", "take_screenshot"):
                        try:
                            facts = await tools.facts()
                            await engine.on_page(facts, step_id)
                            if call.name == "fill_form" and ok:
                                engine.on_form_filled(facts)
                        except PlaywrightError:
                            pass  # page mid-navigation; the next step re-inspects it
                    messages.append({"role": "tool", "tool_call_id": call.id,
                                     "content": rec.redact(obs)[:OBSERVATION_LIMIT]})
                    if call.name == "finish":
                        a = call.arguments
                        outcome = a.get("outcome") or "gave_up"
                        summary = a.get("summary")
                        report = {"price": a.get("price"), "in_stock": a.get("in_stock")}
                        done = True
                        break
                    if idx >= cfg.max_steps:
                        break
    except Exception as exc:
        status, outcome, error = "error", "error", f"{type(exc).__name__}: {str(exc)[:500]}"
    finally:
        if engine is None:
            engine = CheckEngine(rec, cfg.target_product, _NoShots())
        engine.finalize(checkout=cfg.checkout)
        rec.save_score(compute_score(rec.results()))
        rec.finish(status=status, outcome=outcome, step_count=idx, summary=summary, report=report, error=error)
    return rec.run_id


class _NoShots:
    async def screenshot(self, name: str, full_page: bool = False) -> str:
        raise RuntimeError("browser not available")


async def _dispatch(name, args, tools: PageTools, rec, engine, payment: PaymentHandler | None) -> str:
    if name == "open_page":
        return await tools.open_page(args["url"])
    if name == "find_elements":
        return await tools.find_elements(args.get("kind") or "all")
    if name == "read_text":
        return await tools.read_text()
    if name == "click":
        if (await tools.element_tag(args["element_id"])).endswith("paypal-button"):
            raise ToolError("Use pay_with_paypal to pay." if payment else
                            "Payment is not part of this run. Do not click the payment button; call finish.")
        return await tools.click(args["element_id"])
    if name == "fill_form":
        return await tools.fill_form(args["fields"])
    if name == "take_screenshot":
        return await tools.take_screenshot(args.get("label") or "shot")
    if name == "finish":
        return "Run finished."
    if name == "pay_with_paypal" and payment is not None:
        return await payment.pay(tools, rec, engine)
    raise ToolError(f"Unknown tool {name!r}")
