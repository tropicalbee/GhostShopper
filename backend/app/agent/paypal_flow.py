"""pay_with_paypal: click the PayPal button, handle the popup, log in as the sandbox buyer, approve,
then confirm and verify the capture through our backend. Each stage is a scored check.

Credentials: read only from SANDBOX_BUYER_EMAIL / SANDBOX_BUYER_PASSWORD (sandbox mode). They are typed
into the PayPal popup and nowhere else: never returned to the LLM, logged, stored, or screenshotted
(the popup is only captured before anything is typed).

Human approval: if PayPal shows a CAPTCHA, an extra verification step, or a page we don't recognize,
the agent never tries to get past it. The run is marked "awaiting human approval"; a person completes
the PayPal window (headed browser, or Kernel live view); when the window closes the run resumes and the
capture is confirmed as usual.
"""

import asyncio
import base64
import inspect
import re
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable
from urllib.parse import parse_qs, urlparse

import httpx
from playwright.async_api import Error as PlaywrightError
from playwright.async_api import Locator, Page
from playwright.async_api import TimeoutError as PlaywrightTimeout

from .. import db
from ..config import BuyerCredentials, sandbox_buyer
from ..failures import BUYER_SIDE_CAPTURE_ISSUES
from . import checks
from .browser import PageTools, ToolError
from .engine import CheckEngine
from .recorder import RunRecorder


class PaymentConfigError(ValueError):
    pass


@dataclass(frozen=True)
class Timeouts:
    button_s: float
    popup_s: float
    approval_s: float
    capture_s: float
    human_s: float  # how long a human gets to complete a PayPal check

    @property
    def total_s(self) -> float:
        return self.button_s + self.popup_s * 2 + self.approval_s + self.human_s + self.capture_s + 30


MOCK_TIMEOUTS = Timeouts(button_s=10, popup_s=5, approval_s=8, capture_s=8, human_s=20)
LIVE_TIMEOUTS = Timeouts(button_s=20, popup_s=15, approval_s=120, capture_s=45, human_s=600)

# Fake login for the mock popup only (it accepts any non-empty value). Not a real account.
MOCK_BUYER = BuyerCredentials("mock-buyer@example.test", "mock-password")

# The sandbox login/review page ids, with fallbacks. Unverified against live PayPal; adjust after the first live run.
SELECTORS = {
    "email": ["#email", "input[name=login_email]", "input[type=email]"],
    "next": ["#btnNext", "button:has-text('Next')"],
    "password": ["#password", "input[name=login_password]", "input[type=password]"],
    "login": ["#btnLogin", "button:has-text('Log In')"],
    "approve": ["#payment-submit-btn", "button[data-id=payment-submit-btn]",
                "button:has-text('Complete Purchase')", "button:has-text('Pay Now')"],
}
BLOCKER_SELECTORS = ["iframe[src*=captcha i]", "iframe[title*=captcha i]", "[id*=captcha i]", "[class*=captcha i]",
                     "iframe[src*=recaptcha]", "iframe[src*=hcaptcha]"]
BLOCKER_TEXT = re.compile(
    r"captcha|verify (it'?s|it is) you|security (check|challenge)|one-?time (code|passcode)|enter the code|"
    r"we sent (you )?a code|confirm (it'?s|it is) you|are you a robot|i'?m not a robot", re.I)
ISSUE_RE = re.compile(r"\(([A-Z_]{4,})\)")

# PayPal's popup error page: /checkoutweb/genericError?code=<base64 issue name>.
ERROR_PAGE_PATH = "/checkoutweb/genericError"
ERROR_PAGE_HINTS = {
    "CANNOT_PAY_SELF": "The sandbox buyer login is the seller's own account; use the personal sandbox account.",
}

HumanHook = Callable[[dict[str, Any], Page], Awaitable[None] | None]


class _Stuck(Exception):
    pass


class _ErrorPage(Exception):
    def __init__(self, issue: str):
        super().__init__(issue)
        self.issue = issue


def error_page_issue(url: str) -> str | None:
    """The decoded issue name if url is PayPal's error page ('UNKNOWN' if the code can't be read), else None."""
    u = urlparse(url)
    if not u.path.endswith(ERROR_PAGE_PATH):
        return None
    code = (parse_qs(u.query).get("code") or [""])[0]
    try:
        decoded = base64.urlsafe_b64decode(code + "=" * (-len(code) % 4)).decode("ascii", "replace")
    except ValueError:
        decoded = ""
    match = re.match(r"[A-Z][A-Z_]{3,}", decoded)
    return match.group(0) if match else "UNKNOWN"


def _origin(url: str) -> str:
    u = urlparse(url)
    return f"{u.scheme}://{u.netloc}"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


async def popup_state(popup: Page) -> str:
    """error | blocker | approve | password | email | unknown_form | loading. Blockers win over every form:
    if PayPal asks for a human check we never try to continue around it."""
    if error_page_issue(popup.url):
        return "error"
    try:
        for sel in BLOCKER_SELECTORS:
            if await popup.locator(sel).first.is_visible():
                return "blocker"
        text = await popup.evaluate("() => document.body ? document.body.innerText : ''")
        if BLOCKER_TEXT.search(text or ""):
            return "blocker"
        for group in ("approve", "password", "email"):
            for sel in SELECTORS[group]:
                if await popup.locator(sel).first.is_visible():
                    return group
        visible_inputs = await popup.evaluate(
            "() => [...document.querySelectorAll('input, select, textarea')].filter(e => {"
            " const t = (e.type || '').toLowerCase(); if (['hidden','submit','button'].includes(t)) return false;"
            " const r = e.getBoundingClientRect(); return r.width > 0 && r.height > 0; }).length")
        return "unknown_form" if visible_inputs else "loading"
    except PlaywrightError:
        return "loading"


class PayPalCheckout:
    def __init__(self, buyer: BuyerCredentials, api_base: str, timeouts: Timeouts, mode: str,
                 on_awaiting_human: HumanHook | None = None):
        self._buyer = buyer
        self.api_base = api_base.rstrip("/")
        self.timeouts = timeouts
        self.mode = mode
        self.on_awaiting_human = on_awaiting_human
        self._hook_tasks: set[asyncio.Task] = set()

    @property
    def secrets(self) -> tuple[str, ...]:
        return (self._buyer.email, self._buyer.password)

    @property
    def max_duration_s(self) -> float:
        return self.timeouts.total_s

    async def _status_text(self, page: Page) -> str:
        try:
            return (await page.evaluate(
                "() => ['#checkout-status', '#paypal-unavailable'].map(s => document.querySelector(s))"
                ".filter(Boolean).map(e => e.textContent.trim()).filter(Boolean).join(' ')"
            ))[:300]
        except PlaywrightError:
            return ""

    async def _fail(self, rec: RunRecorder, tools: PageTools, key: str, code: str, reason: str,
                    evidence: dict[str, Any]) -> str:
        # Evidence is the store page only. Never the popup, which may hold typed credentials.
        try:
            evidence["screenshot"] = await tools.screenshot(f"check-{key}", full_page=True)
        except PlaywrightError:
            pass
        rec.record_check(key, False, reason, evidence, code=code)
        return f"Payment failed: {reason}"

    async def pay(self, tools: PageTools, rec: RunRecorder, engine: CheckEngine) -> str:
        page = tools.page
        if not checks.is_checkout_page(await tools.facts()):
            raise ToolError("pay_with_paypal works only on the checkout page. Go to checkout first.")
        if rec.is_recorded("paypal_button_found"):
            raise ToolError("Payment was already attempted in this run.")
        t = self.timeouts

        # 1. PayPal button rendered by the SDK.
        button = page.locator("paypal-button").first
        try:
            await button.wait_for(state="visible", timeout=t.button_s * 1000)
        except PlaywrightTimeout:
            status = await self._status_text(page)
            return await self._fail(rec, tools, "paypal_button_found", "paypal_button_missing",
                                    f"No visible PayPal button after {t.button_s:.0f}s." + (f" Page says: {status}" if status else ""),
                                    {"url": page.url, "selector": "paypal-button", "status_text": status})
        rec.record_check("paypal_button_found", True, "PayPal button visible on checkout.",
                         {"url": page.url, "selector": "paypal-button"})

        # 2. Click opens the PayPal window.
        try:
            async with page.expect_popup(timeout=t.popup_s * 1000) as popup_info:
                await button.click(timeout=5_000)
            popup = await popup_info.value
        except PlaywrightTimeout:
            await page.wait_for_timeout(300)
            status = await self._status_text(page)
            blocked = "blocked" in status.lower()
            return await self._fail(rec, tools, "popup_opened",
                                    "popup_blocked_by_browser" if blocked else "popup_not_opened",
                                    f"PayPal window did not open within {t.popup_s:.0f}s"
                                    + (" (the browser blocked it)." if blocked else ".")
                                    + (f" Page says: {status}" if status else ""),
                                    {"url": page.url, "selector": "paypal-button", "status_text": status})
        evidence: dict[str, Any] = {"url": page.url}
        try:
            # The SDK opens about:blank synchronously, then points it at PayPal once the order exists.
            settle = time.monotonic() + t.popup_s
            while popup.url in ("", "about:blank") and time.monotonic() < settle:
                await popup.wait_for_timeout(100)
            await popup.wait_for_load_state("domcontentloaded", timeout=t.popup_s * 1000)
            evidence["popup_url"] = popup.url.split("?")[0]
            evidence["screenshot"] = await self._popup_shot(tools, popup)  # before anything is typed
        except PlaywrightError:
            pass
        rec.record_check("popup_opened", True, "PayPal window opened from the button click.", evidence)

        # 3. Log in and approve; hand over to a human if PayPal asks for a check we must not automate.
        try:
            approved_by = await self._login_and_approve(popup, rec, tools)
        except _Stuck as exc:
            await self._close(popup)
            return await self._fail(rec, tools, "payment_approved", "approval_timeout",
                                    f"Approval did not complete within {t.approval_s:.0f}s (stuck {exc}).",
                                    {"url": page.url})
        except _ErrorPage as exc:
            await self._close(popup)
            hint = ERROR_PAGE_HINTS.get(exc.issue)
            return await self._fail(rec, tools, "payment_approved", "paypal_error_page",
                                    f"PayPal showed its error page ({exc.issue})." + (f" {hint}" if hint else ""),
                                    {"url": page.url, "issue": exc.issue})
        if approved_by == "human_timeout":
            return await self._fail(rec, tools, "payment_approved", "human_approval_timeout",
                                    f"PayPal asked for a human check and nobody completed it within {t.human_s:.0f}s.",
                                    {"url": page.url})

        # 4. The store captures on approval and shows a confirmation, or an error / cancellation.
        result, detail = await self._wait_for_result(page, t.capture_s)
        if result == "cancelled":
            return await self._fail(rec, tools, "payment_approved", "approval_cancelled",
                                    f"The payment was cancelled in the PayPal window. Page says: {detail}",
                                    {"url": page.url, "status_text": detail, "approved_by": approved_by})
        rec.record_check("payment_approved", True,
                         "Buyer logged in and approved the payment." if approved_by == "agent"
                         else "A human completed PayPal's check and approved the payment.",
                         {"url": page.url, "approved_by": approved_by})
        if result != "thanks":
            issue_match = ISSUE_RE.search(detail or "")
            issue = issue_match.group(1) if issue_match else None
            if result == "error":
                code = "capture_declined" if issue in BUYER_SIDE_CAPTURE_ISSUES else "capture_error"
            else:
                code = "capture_unconfirmed"
            reason = {"capture_declined": f"The buyer's funding source declined the payment ({issue}).",
                      "capture_error": f"Capture failed after approval{f' ({issue})' if issue else ''}.",
                      "capture_unconfirmed": "No confirmation page after approval."}[code]
            return await self._fail(rec, tools, "capture_completed", code,
                                    reason + (f" Page says: {detail}" if detail else ""),
                                    {"url": page.url, "status_text": detail, "issue": issue})

        order_id = (parse_qs(urlparse(page.url).query).get("order") or [""])[0]
        order = await self._backend_get(f"/api/paypal/orders/{order_id}") if order_id else None
        ok = (order is not None and order.get("status") == "COMPLETED"
              and order.get("capture_status") == "COMPLETED" and order.get("capture_id"))
        if not ok:
            return await self._fail(rec, tools, "capture_completed", "capture_unconfirmed",
                                    f"Backend does not confirm a completed capture for order {order_id or '(none)'}.",
                                    {"url": page.url, "order_id": order_id, "backend_order": order})
        linked = db.link_order_to_run(rec.db_path, order_id, rec.run_id)
        summary = {k: order.get(k) for k in ("order_id", "capture_id", "status", "capture_status", "amount",
                                             "currency", "gross_amount", "paypal_fee", "net_amount")}
        if not linked:
            summary["note"] = "order not found in this run's database; not linked"
        rec.record_check("capture_completed", True, f"Order {order_id} captured ({order.get('capture_id')}).",
                         {"url": page.url, **summary})

        # 5. Verification: order <-> capture <-> advertised amount <-> fees.
        verification = await self._backend_get(f"/api/paypal/orders/{order_id}/verify")
        if verification is None:
            rec.record_check("payment_verified", False, "The backend could not verify the order.",
                             {"order_id": order_id}, code="verification_unavailable")
        elif verification["ok"]:
            rec.record_check("payment_verified", True, "Order, capture, advertised amount and fees all match.",
                             {"order_id": order_id, "checked": verification["checked"]})
        else:
            first = verification["mismatches"][0]
            rec.record_check("payment_verified", False,
                             "; ".join(m["detail"] for m in verification["mismatches"]),
                             {"order_id": order_id, "mismatches": verification["mismatches"],
                              "checked": verification["checked"]}, code=verification["code"] or first["code"])
        approved_note = " A human completed PayPal's extra check." if approved_by == "human" else ""
        verdict = "verified" if verification and verification["ok"] else "NOT verified"
        return (f"Payment complete.{approved_note} Order {order_id}, capture {order.get('capture_id')}, status "
                f"{order.get('status')}, amount {order.get('amount')} {order.get('currency')}, "
                f"PayPal fee {order.get('paypal_fee')}, net {order.get('net_amount')}. Payment {verdict}.")

    async def _login_and_approve(self, popup: Page, rec: RunRecorder, tools: PageTools) -> str:
        """Returns 'agent' | 'human' | 'human_timeout'. Raises _Stuck on approval timeout, _ErrorPage if
        PayPal shows its error page."""
        deadline = time.monotonic() + self.timeouts.approval_s
        typed: set[str] = set()
        state = "loading"
        while True:
            if popup.is_closed():
                return "agent"
            state = await popup_state(popup)
            if state == "error":
                raise _ErrorPage(error_page_issue(popup.url) or "UNKNOWN")
            if state in ("blocker", "unknown_form"):
                reason = ("PayPal is asking for a CAPTCHA or extra verification." if state == "blocker"
                          else "PayPal showed a page the agent does not recognize.")
                return await self._await_human(popup, rec, tools, state, reason)
            if state == "approve":
                await self._click_first(popup, "approve")
                # Poll rather than wait for close: PayPal may answer the approval with its error page.
                while not popup.is_closed():
                    issue = error_page_issue(popup.url)
                    if issue:
                        raise _ErrorPage(issue)
                    if time.monotonic() > deadline:
                        raise _Stuck("waiting for the PayPal window to close")
                    try:
                        await popup.wait_for_timeout(250)
                    except PlaywrightError:
                        break  # closed while waiting
                return "agent"
            if state == "email" and "email" not in typed:
                await self._fill_first(popup, "email", self._buyer.email)
                typed.add("email")
                if not await self._click_first(popup, "next"):
                    await popup.keyboard.press("Enter")
            elif state == "password" and "password" not in typed:
                await self._fill_first(popup, "password", self._buyer.password)
                typed.add("password")
                if not await self._click_first(popup, "login"):
                    await popup.keyboard.press("Enter")
            if time.monotonic() > deadline:
                raise _Stuck(f"at '{state}'")
            await popup.wait_for_timeout(200)

    async def _await_human(self, popup: Page, rec: RunRecorder, tools: PageTools, stage: str, reason: str) -> str:
        session = tools.s
        info = {
            "stage": stage, "reason": reason, "since": _now(), "timeout_s": self.timeouts.human_s,
            "popup_url": popup.url.split("?")[0], "live_view_url": getattr(session, "live_view_url", None),
            "headless": getattr(session, "headless", True),
            "instructions": "Complete the PayPal window (log in, pass the check, approve). The run resumes when it closes.",
        }
        rec.set_awaiting(info)
        try:
            if self.on_awaiting_human:
                result = self.on_awaiting_human(info, popup)
                if inspect.isawaitable(result):
                    task = asyncio.ensure_future(result)  # the human acts while we wait for the window to close
                    self._hook_tasks.add(task)
                    task.add_done_callback(self._hook_tasks.discard)
            try:
                if not popup.is_closed():
                    await popup.wait_for_event("close", timeout=self.timeouts.human_s * 1000)
            except PlaywrightTimeout:
                await self._close(popup)
                return "human_timeout"
            return "human"
        finally:
            rec.set_awaiting(None)

    async def _fill_first(self, page: Page, group: str, value: str) -> None:
        for sel in SELECTORS[group]:
            loc = page.locator(sel).first
            if await loc.is_visible():
                await loc.fill(value)
                return

    async def _click_first(self, page: Page, group: str) -> bool:
        for sel in SELECTORS[group]:
            loc: Locator = page.locator(sel).first
            try:
                if await loc.is_visible():
                    await loc.click()
                    return True
            except PlaywrightError:
                pass
        return False

    async def _close(self, popup: Page) -> None:
        try:
            if not popup.is_closed():
                await popup.close()
        except PlaywrightError:
            pass

    async def _popup_shot(self, tools: PageTools, popup: Page) -> str:
        tools.shots_dir.mkdir(parents=True, exist_ok=True)
        path = tools.shots_dir / "paypal-popup-before-login.png"
        await popup.screenshot(path=str(path))
        return path.as_posix()

    async def _wait_for_result(self, page: Page, timeout_s: float) -> tuple[str, str]:
        """thanks | error | cancelled | timeout, with the page's status text."""
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            try:
                if "/thanks" in urlparse(page.url).path:
                    await page.wait_for_load_state("load", timeout=5_000)
                    return "thanks", ""
                err = await page.evaluate(
                    "() => { const e = document.querySelector('#checkout-status.errors'); return e ? e.textContent.trim() : ''; }")
                if err:
                    return "error", err[:300]
                status = await self._status_text(page)
                if "cancel" in status.lower():
                    return "cancelled", status
            except PlaywrightError:
                pass  # navigating to the confirmation page
            await page.wait_for_timeout(250)
        return "timeout", await self._status_text(page)

    async def _backend_get(self, path: str) -> dict[str, Any] | None:
        async with httpx.AsyncClient(timeout=10.0) as http:
            resp = await http.get(f"{self.api_base}{path}")
        return resp.json() if resp.status_code == 200 else None


def make_payment_handler(
    mode: str,
    store_url: str,
    server_mode: str | None = None,
    server_configured: bool | None = None,
    on_awaiting_human: HumanHook | None = None,
) -> PayPalCheckout:
    """Live sandbox only when every credential is present and the server agrees; never a silent fallback."""
    api_base = _origin(store_url)
    if server_mode is None:
        try:
            health = httpx.get(f"{api_base}/api/health", timeout=10.0).json()
        except httpx.HTTPError as exc:
            raise PaymentConfigError(f"Cannot reach the server at {api_base}: {exc}") from exc
        server_mode = health.get("paypal_mode", "sandbox")
        server_configured = bool(health.get("paypal_configured"))
    if server_mode != mode:
        raise PaymentConfigError(
            f"Checkout mode '{mode}' requested, but the server runs PAYPAL_MODE={server_mode}. "
            f"Restart the server with PAYPAL_MODE={mode}, or run with --paypal {server_mode}.")
    if mode == "mock":
        return PayPalCheckout(MOCK_BUYER, api_base, MOCK_TIMEOUTS, mode, on_awaiting_human)
    if mode != "sandbox":
        raise PaymentConfigError(f"Unknown PayPal mode {mode!r}")
    missing = []
    if not server_configured:
        missing.append("PAYPAL_CLIENT_ID / PAYPAL_CLIENT_SECRET on the server")
    buyer = sandbox_buyer()
    if buyer is None:
        missing.append("SANDBOX_BUYER_EMAIL / SANDBOX_BUYER_PASSWORD")
    if missing:
        raise PaymentConfigError(
            "Live sandbox checkout disabled; missing " + " and ".join(missing)
            + ". Use a PAYPAL_MODE=mock server with --paypal mock to test the checkout path.")
    return PayPalCheckout(buyer, api_base, LIVE_TIMEOUTS, mode, on_awaiting_human)
