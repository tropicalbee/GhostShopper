"""pay_with_paypal: click the PayPal button, handle the popup, log in as the sandbox buyer, approve,
then confirm the capture through our backend. Each stage is a scored check.

Credentials: read only from SANDBOX_BUYER_EMAIL / SANDBOX_BUYER_PASSWORD (sandbox mode). They are typed
into the PayPal popup and nowhere else: never returned to the LLM, logged, stored, or screenshotted
(the popup is only captured before anything is typed).
"""

import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import parse_qs, urlparse

import httpx
from playwright.async_api import Error as PlaywrightError
from playwright.async_api import Locator, Page
from playwright.async_api import TimeoutError as PlaywrightTimeout

from .. import db
from ..config import BuyerCredentials, sandbox_buyer
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


MOCK_TIMEOUTS = Timeouts(button_s=10, popup_s=5, approval_s=8, capture_s=8)
LIVE_TIMEOUTS = Timeouts(button_s=20, popup_s=15, approval_s=120, capture_s=45)

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


class _Stuck(Exception):
    pass


async def _first_visible(page: Page, groups: list[str], deadline: float) -> tuple[str, Locator]:
    """Poll until any selector of the named groups is visible. Returns (group, locator)."""
    while time.monotonic() < deadline:
        for group in groups:
            for sel in SELECTORS[group]:
                loc = page.locator(sel).first
                try:
                    if await loc.is_visible():
                        return group, loc
                except PlaywrightError:
                    pass  # page navigating
        await page.wait_for_timeout(200)
    raise _Stuck(f"waiting for {' or '.join(groups)}")


def _origin(url: str) -> str:
    u = urlparse(url)
    return f"{u.scheme}://{u.netloc}"


class PayPalCheckout:
    def __init__(self, buyer: BuyerCredentials, api_base: str, timeouts: Timeouts, mode: str):
        self._buyer = buyer
        self.api_base = api_base.rstrip("/")
        self.timeouts = timeouts
        self.mode = mode

    @property
    def secrets(self) -> tuple[str, ...]:
        return (self._buyer.email, self._buyer.password)

    async def _status_text(self, page: Page) -> str:
        try:
            return (await page.evaluate(
                "() => ['#checkout-status', '#paypal-unavailable'].map(s => document.querySelector(s))"
                ".filter(Boolean).map(e => e.textContent.trim()).filter(Boolean).join(' ')"
            ))[:300]
        except PlaywrightError:
            return ""

    async def _fail(self, rec: RunRecorder, tools: PageTools, key: str, reason: str, evidence: dict[str, Any]) -> str:
        # Evidence is the store page only. Never the popup, which may hold typed credentials.
        try:
            evidence["screenshot"] = await tools.screenshot(f"check-{key}", full_page=True)
        except PlaywrightError:
            pass
        rec.record_check(key, False, reason, evidence)
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
            return await self._fail(rec, tools, "paypal_button_found",
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
            return await self._fail(rec, tools, "popup_opened",
                                    f"PayPal window did not open within {t.popup_s:.0f}s (popup blocked?)."
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

        # 3. Log in and approve, within one overall deadline.
        deadline = time.monotonic() + t.approval_s
        stage = "login"
        try:
            group, loc = await _first_visible(popup, ["email", "password", "approve"], deadline)
            if group == "email":
                stage = "email"
                await loc.fill(self._buyer.email)
                nxt = await self._optional(popup, "next")
                if nxt:
                    await nxt.click()
                group, loc = await _first_visible(popup, ["password", "approve"], deadline)
            if group == "password":
                stage = "password"
                await loc.fill(self._buyer.password)
                login = await self._optional(popup, "login")
                if login:
                    await login.click()
                else:
                    await loc.press("Enter")
                group, loc = await _first_visible(popup, ["approve"], deadline)
            stage = "approve"
            await loc.click()
            stage = "PayPal window closing"
            remaining = max(deadline - time.monotonic(), 1)
            if not popup.is_closed():
                await popup.wait_for_event("close", timeout=remaining * 1000)
        except (_Stuck, PlaywrightTimeout) as exc:
            detail = str(exc) if isinstance(exc, _Stuck) else stage
            try:
                await popup.close()
            except PlaywrightError:
                pass
            return await self._fail(rec, tools, "payment_approved",
                                    f"Approval did not complete within {t.approval_s:.0f}s (stuck {detail}).",
                                    {"url": page.url, "stage": stage})
        rec.record_check("payment_approved", True, "Buyer logged in and approved the payment.", {"url": page.url})

        # 4. The store captures on approval and shows a confirmation; confirm it through our backend.
        result, detail = await self._wait_for_result(page, t.capture_s)
        if result != "thanks":
            return await self._fail(rec, tools, "capture_completed",
                                    f"No confirmation page after approval ({result}). " + (f"Page says: {detail}" if detail else ""),
                                    {"url": page.url, "status_text": detail})
        order_id = (parse_qs(urlparse(page.url).query).get("order") or [""])[0]
        order = await self._backend_order(order_id)
        ok = (order is not None and order.get("status") == "COMPLETED"
              and order.get("capture_status") == "COMPLETED" and order.get("capture_id"))
        if not ok:
            return await self._fail(rec, tools, "capture_completed",
                                    f"Backend does not confirm a completed capture for order {order_id or '(none)'}.",
                                    {"url": page.url, "order_id": order_id, "backend_order": order})
        linked = db.link_order_to_run(rec.db_path, order_id, rec.run_id)
        summary = {k: order.get(k) for k in ("order_id", "capture_id", "status", "capture_status", "amount",
                                             "currency", "gross_amount", "paypal_fee", "net_amount")}
        if not linked:
            summary["note"] = "order not found in this run's database; not linked"
        rec.record_check("capture_completed", True, f"Order {order_id} captured ({order.get('capture_id')}).",
                         {"url": page.url, **summary})
        return (f"Payment complete. Order {order_id}, capture {order.get('capture_id')}, status "
                f"{order.get('status')}, amount {order.get('amount')} {order.get('currency')}, "
                f"PayPal fee {order.get('paypal_fee')}, net {order.get('net_amount')}.")

    async def _optional(self, page: Page, group: str) -> Locator | None:
        for sel in SELECTORS[group]:
            loc = page.locator(sel).first
            try:
                if await loc.is_visible():
                    return loc
            except PlaywrightError:
                pass
        return None

    async def _popup_shot(self, tools: PageTools, popup: Page) -> str:
        tools.shots_dir.mkdir(parents=True, exist_ok=True)
        path = tools.shots_dir / "paypal-popup-before-login.png"
        await popup.screenshot(path=str(path))
        return path.as_posix()

    async def _wait_for_result(self, page: Page, timeout_s: float) -> tuple[str, str]:
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
            except PlaywrightError:
                pass  # navigating to the confirmation page
            await page.wait_for_timeout(250)
        return "timeout", await self._status_text(page)

    async def _backend_order(self, order_id: str) -> dict[str, Any] | None:
        if not order_id:
            return None
        async with httpx.AsyncClient(timeout=10.0) as http:
            resp = await http.get(f"{self.api_base}/api/paypal/orders/{order_id}")
        return resp.json() if resp.status_code == 200 else None


def make_payment_handler(
    mode: str,
    store_url: str,
    server_mode: str | None = None,
    server_configured: bool | None = None,
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
        return PayPalCheckout(MOCK_BUYER, api_base, MOCK_TIMEOUTS, mode)
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
    return PayPalCheckout(buyer, api_base, LIVE_TIMEOUTS, mode)
