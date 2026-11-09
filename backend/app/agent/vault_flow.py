"""pay_with_saved_paypal: pay with the buyer's saved PayPal account (Vault), the way a real AI shopping agent would.

No popup, no password. The buyer approved PayPal once (`python -m backend.app.vault setup`) and PayPal gave us a
payment token. The agent asks the store's own server to take that payment (POST /api/paypal/agent-orders), so the
test is still "does this store accept an agent payment". The token is never returned to the LLM: it is read from
SQLite by this handler, sent only to the store's endpoint, and registered as a secret so the recorder redacts it.

Docs: https://developer.paypal.com/docs/api/orders/v2/ (payment_source.paypal.vault_id)
"""

import os
import uuid
from decimal import Decimal
from urllib.parse import parse_qs, urlparse

import httpx
from playwright.async_api import Error as PlaywrightError
from playwright.async_api import TimeoutError as PlaywrightTimeout

from store.app import ADMIN_COOKIE

from .. import db
from ..failures import BUYER_SIDE_CAPTURE_ISSUES
from ..vault import VaultError, load_token
from . import checks
from .browser import PageTools, ToolError
from .engine import CheckEngine
from .paypal_flow import PaymentConfigError, PayPalCheckout, _origin
from .recorder import RunRecorder

TOOL_NAME = "pay_with_saved_paypal"
BUTTON_WAIT_S = {"mock": 10.0, "sandbox": 30.0}
REQUEST_TIMEOUT_S = 60.0


class VaultPayment:
    tool_name = TOOL_NAME

    def __init__(self, vault_id: str, customer_id: str | None, api_base: str, mode: str):
        self._vault_id = vault_id
        self.api_base = api_base.rstrip("/")
        self.mode = mode
        self.secrets = tuple(s for s in (vault_id, customer_id) if s)
        self.max_duration_s = BUTTON_WAIT_S[mode] + REQUEST_TIMEOUT_S + 30

    async def _fail(self, rec: RunRecorder, tools: PageTools, key: str, code: str, reason: str, evidence: dict) -> str:
        try:
            evidence["screenshot"] = await tools.screenshot(f"check-{key}", full_page=True)
        except PlaywrightError:
            pass
        rec.record_check(key, False, reason, evidence, code=code)
        return f"Payment failed: {reason}"

    async def _get(self, path: str) -> dict | None:
        async with httpx.AsyncClient(timeout=10.0) as http:
            resp = await http.get(f"{self.api_base}{path}")
        return resp.json() if resp.status_code == 200 else None

    def _no_popup_checks(self, rec: RunRecorder, url: str) -> None:
        rec.record_check("popup_opened", True, "No PayPal window needed: paid with a saved PayPal account.",
                         {"url": url, "payment": "vault"})
        rec.record_check("payment_approved", True, "The buyer's saved PayPal account (Vault) approved the payment.",
                         {"url": url, "payment": "vault"})

    async def pay(self, tools: PageTools, rec: RunRecorder, engine: CheckEngine) -> str:
        page = tools.page
        facts = await tools.facts()
        if not checks.is_checkout_page(facts):
            raise ToolError(f"{TOOL_NAME} works only on the checkout page. Go to checkout first.")
        if rec.is_recorded("paypal_button_found"):
            raise ToolError("Payment was already attempted in this run.")
        sku = (parse_qs(urlparse(page.url).query).get("sku") or [""])[0]
        if not sku:
            raise ToolError("The checkout page URL has no product (sku), so the order cannot be built.")

        if facts.get("has_password_field") and not facts.get("has_payment_button"):
            # Same finding as the engine's: an account wall instead of a PayPal option. Never get past it.
            reason = "Checkout asks the shopper to create an account with a password before any PayPal button appears."
            rec.record_check("paypal_button_found", False, reason,
                             {"url": page.url, "selector": "input[type=password]"}, code="account_required")
            return f"Not paid: {reason} Call finish and report that checkout needs an account."

        # 1. The store should still offer PayPal on checkout; an agent that pays by token still needs that to be there.
        wait_s = BUTTON_WAIT_S[self.mode]
        try:
            await page.locator("paypal-button").first.wait_for(state="visible", timeout=wait_s * 1000)
        except PlaywrightTimeout:
            return await self._fail(rec, tools, "paypal_button_found", "paypal_button_missing",
                                    f"No visible PayPal button after {wait_s:.0f}s.",
                                    {"url": page.url, "selector": "paypal-button"})
        engine.paypal.note_button(page.url, True, "paypal-button")

        def button_ok() -> None:  # recorded after the over-budget refusal, which owns this check when it fires
            rec.record_check("paypal_button_found", True, "PayPal button visible on checkout.",
                             {"url": page.url, "selector": "paypal-button"})

        # 2. The store takes the agent payment. The spending limit is checked by the endpoint before PayPal is called.
        body = {"sku": sku, "quantity": 1, "vault_id": self._vault_id, "request_id": f"ghost-{uuid.uuid4().hex}"}
        if engine.budget is not None:
            body["max_amount"] = f"{engine.budget:.2f}"
        try:
            token = os.getenv("DEMO_ADMIN_TOKEN", "").strip()  # presenter unlock on a deployed server
            cookies = {ADMIN_COOKIE: token} if token else {}
            async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_S, cookies=cookies) as http:
                resp = await http.post(f"{self.api_base}/api/paypal/agent-orders", json=body)
        except httpx.HTTPError as exc:
            button_ok()
            return await self._fail(rec, tools, "payment_approved", "capture_error",
                                    f"The store's agent payment endpoint could not be reached ({type(exc).__name__}).",
                                    {"url": page.url})
        if resp.status_code != 201:
            detail: dict = {}
            try:
                parsed = resp.json().get("detail")
                detail = parsed if isinstance(parsed, dict) else {}
            except ValueError:
                pass
            if resp.status_code == 403 and detail.get("error") == "ACCOUNT_REQUIRED":
                return await self._fail(rec, tools, "paypal_button_found", "account_required",
                                        "Checkout asks the shopper to create an account before any payment.",
                                        {"url": page.url})
            if resp.status_code == 409 and detail.get("error") == "OVER_BUDGET":
                refused = await engine.stop_if_order_over_budget(Decimal(detail["amount"]), facts)
                return f"{refused} Do not try again; call finish and tell the customer why."
            button_ok()
            issue = detail.get("issue")
            message = str(detail.get("message") or f"HTTP {resp.status_code}")[:200]
            if resp.status_code == 422 and issue in BUYER_SIDE_CAPTURE_ISSUES:
                self._no_popup_checks(rec, page.url)
                return await self._fail(rec, tools, "capture_completed", "capture_declined",
                                        f"The buyer's funding source declined the payment ({issue}).",
                                        {"url": page.url, "issue": issue})
            if resp.status_code == 422:
                return await self._fail(rec, tools, "payment_approved", "vault_payment_refused",
                                        f"PayPal refused the saved payment token ({issue or message}).",
                                        {"url": page.url, "issue": issue})
            return await self._fail(rec, tools, "payment_approved", "capture_error",
                                    f"The store's agent payment failed: {message}", {"url": page.url, "issue": issue})

        button_ok()
        self._no_popup_checks(rec, page.url)

        # 3. Same recording and verification as the popup flow, read back from the backend.
        order_id = resp.json()["order_id"]
        stored = await self._get(f"/api/paypal/orders/{order_id}")
        ok = (stored is not None and stored.get("status") == "COMPLETED"
              and stored.get("capture_status") == "COMPLETED" and stored.get("capture_id"))
        if not ok:
            return await self._fail(rec, tools, "capture_completed", "capture_unconfirmed",
                                    f"Backend does not confirm a completed capture for order {order_id}.",
                                    {"url": page.url, "order_id": order_id, "backend_order": stored})
        linked = db.link_order_to_run(rec.db_path, order_id, rec.run_id)
        summary = {k: stored.get(k) for k in ("order_id", "capture_id", "status", "capture_status", "amount",
                                              "currency", "gross_amount", "paypal_fee", "net_amount")}
        if not linked:
            summary["note"] = "order not found in this run's database; not linked"
        rec.record_check("capture_completed", True, f"Order {order_id} captured ({stored.get('capture_id')}).",
                         {"url": page.url, **summary})

        verification = await self._get(f"/api/paypal/orders/{order_id}/verify")
        budget_evidence = PayPalCheckout._budget_evidence(engine.budget, stored)
        extra = {"budget": budget_evidence} if budget_evidence else {}
        within = not (budget_evidence and not budget_evidence["within"])
        if verification is None:
            rec.record_check("payment_verified", False, "The backend could not verify the order.",
                             {"order_id": order_id, **extra}, code="verification_unavailable")
        elif verification["ok"] and not within:
            rec.record_check("payment_verified", False,
                             f"Captured {budget_evidence['captured']} is over the {budget_evidence['limit']} spending limit.",
                             {"order_id": order_id, "checked": verification["checked"], **extra}, code="amount_mismatch")
        elif verification["ok"]:
            rec.record_check("payment_verified", True,
                             "Order, capture, advertised amount and fees all match"
                             + (f", and {budget_evidence['captured']} is within the {budget_evidence['limit']} limit."
                                if budget_evidence else "."),
                             {"order_id": order_id, "checked": verification["checked"], **extra})
        else:
            first = verification["mismatches"][0]
            rec.record_check("payment_verified", False, "; ".join(m["detail"] for m in verification["mismatches"]),
                             {"order_id": order_id, "mismatches": verification["mismatches"],
                              "checked": verification["checked"], **extra}, code=verification["code"] or first["code"])
        verdict = "verified" if verification and verification["ok"] and within else "NOT verified"
        return (f"Payment complete (saved PayPal account, no popup). Order {order_id}, capture {stored.get('capture_id')}, "
                f"status {stored.get('status')}, amount {stored.get('amount')} {stored.get('currency')}, "
                f"PayPal fee {stored.get('paypal_fee')}, net {stored.get('net_amount')}. Payment {verdict}.")


def make_vault_handler(mode: str, store_url: str, db_path, server_mode: str | None = None,
                       server_configured: bool | None = None) -> VaultPayment:
    """A missing token, or a server in another PayPal mode, is an explicit error: never a silent fallback."""
    api_base = _origin(store_url)
    if server_mode is None:
        try:
            health = httpx.get(f"{api_base}/api/health", timeout=10.0).json()
        except httpx.HTTPError as exc:
            raise PaymentConfigError(f"Cannot reach the server at {api_base}: {exc}") from exc
        server_mode, server_configured = health.get("paypal_mode", "sandbox"), bool(health.get("paypal_configured"))
    if server_mode != mode:
        raise PaymentConfigError(
            f"Checkout mode '{mode}' requested, but the server runs PAYPAL_MODE={server_mode}. "
            f"Restart the server with PAYPAL_MODE={mode}, or run with --paypal {server_mode}.")
    if mode == "sandbox" and not server_configured:
        raise PaymentConfigError(
            "Live sandbox checkout disabled; missing PAYPAL_CLIENT_ID / PAYPAL_CLIENT_SECRET on the server.")
    try:
        token = load_token(db_path, mode)
    except VaultError as exc:
        raise PaymentConfigError(str(exc)) from exc
    return VaultPayment(token["payment_token_id"], token["customer_id"], api_base, mode)
