"""PAYPAL_MODE=mock: a fake Orders v2 client plus a mock v6 JS SDK and popup.

No PayPal servers are contacted. The popup imitates the sandbox login/approve pages (same element ids)
so the agent's PayPal flow runs unchanged. Scenarios simulate the checkout failures the score checks for.
"""

import base64
import html
import json
import uuid
from datetime import datetime, timezone
from decimal import ROUND_HALF_UP, Decimal
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, Response
from pydantic import BaseModel

from .paypal import PayPalError, check_search_window

MOCK_CLIENT_ID = "mock-client-id"
MOCK_SDK_PATH = "/mock-paypal/sdk.js"
SCENARIOS = ("ok", "no_button", "popup_blocked", "approval_stuck", "capture_declined",
             "captcha", "verification_required", "capture_amount_mismatch", "fee_mismatch", "seller_login",
             "buyer_cancels", "first_attempt_fails")
Scenario = Literal["ok", "no_button", "popup_blocked", "approval_stuck", "capture_declined",
                   "captcha", "verification_required", "capture_amount_mismatch", "fee_mismatch", "seller_login",
                   "buyer_cancels", "first_attempt_fails"]
# seller_login: the buyer logs in with the seller's account and PayPal answers with its error page.
# buyer_cancels: the buyer logs in, then cancels in the PayPal window.
# first_attempt_fails: PayPal answers the first capture with a temporary 503; the next capture works.
SELLER_LOGIN_ERROR_CODE = base64.urlsafe_b64encode(b"CANNOT_PAY_SELF").decode().rstrip("=")

# PayPal US standard checkout rate, used only to make fake fee numbers realistic.
FEE_RATE = Decimal("0.0349")
FEE_FIXED = Decimal("0.49")


def _money(d: Decimal) -> str:
    return str(d.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def _reporting_row(transaction_id: str, event_code: str, status: str, amount: dict[str, str],
                   fee: dict[str, str] | None, reference_id: str, reference_type: str) -> dict[str, Any]:
    now = datetime.now(timezone.utc).isoformat()
    info: dict[str, Any] = {
        "transaction_id": transaction_id, "transaction_event_code": event_code, "transaction_status": status,
        "transaction_initiation_date": now, "transaction_updated_date": now,
        "transaction_amount": amount, "paypal_reference_id": reference_id, "paypal_reference_id_type": reference_type,
    }
    if fee is not None:
        info["fee_amount"] = fee  # negative, as PayPal reports it
    return {"transaction_info": info, "payer_info": {}, "shipping_info": {}, "cart_info": {}}


class FakePayPalClient:
    """Same interface as PayPalClient. Keeps orders in memory."""

    def __init__(self):
        self.orders: dict[str, dict[str, Any]] = {}
        self.scenario: str = "ok"
        self.transient_failure_sent = False  # first_attempt_fails: the one temporary failure has been used
        self.captures: dict[str, dict[str, str]] = {}  # capture id -> amount, so a refund can return it
        self.refunds: dict[str, dict[str, Any]] = {}
        # Vaulted orders: True = answer COMPLETED with the capture inside (what PayPal usually does);
        # False = answer CREATED so the caller has to capture.
        self.vault_completes_immediately: bool = True
        # Transaction Search: what this process captured and refunded, as reporting rows. Another process's orders
        # are not here, so they read as "not in reporting yet", which is what a real delay looks like.
        self.transactions: list[dict[str, Any]] = []
        self.reporting_lag = False  # True = reporting has not caught up: searches find nothing
        self.report_overrides: dict[str, dict[str, str]] = {}  # capture id -> {"amount"|"fee"|"status": ...} PayPal reports differently
        self.search_error: PayPalError | None = None  # raised by search_transactions (for permission-error tests)
        self.searches: list[tuple[datetime, datetime, str | None]] = []
        self.request_ids: dict[str, dict[str, Any]] = {}  # PayPal-Request-Id -> first response: a retry returns it, not a second order

    async def aclose(self) -> None:
        pass

    async def create_order(self, purchase_unit: dict[str, Any]) -> dict[str, Any]:
        order_id = "MOCK" + uuid.uuid4().hex[:13].upper()
        self.orders[order_id] = {"purchase_unit": purchase_unit, "status": "CREATED"}
        return {"id": order_id, "status": "CREATED"}

    async def create_setup_token(self, return_url: str, cancel_url: str) -> dict[str, Any]:
        token = "MOCKSETUP" + uuid.uuid4().hex[:10].upper()
        return {"id": token, "status": "PAYER_ACTION_REQUIRED",
                "customer": {"id": "mock_customer_" + uuid.uuid4().hex[:8]},
                "links": [{"rel": "approve", "method": "GET", "href": f"{return_url}?approval_token_id={token}"}]}

    async def create_payment_token(self, setup_token_id: str) -> dict[str, Any]:
        # Stateless on purpose: the CLI and the server are different processes, each with its own fake client.
        if not setup_token_id.startswith("MOCKSETUP"):
            raise PayPalError(404, {"name": "RESOURCE_NOT_FOUND", "details": [{"issue": "INVALID_RESOURCE_ID"}]})
        return {"id": "MOCKVAULT" + uuid.uuid4().hex[:8].upper(), "status": "CREATED",
                "customer": {"id": "mock_customer_" + uuid.uuid4().hex[:8]},
                "payment_source": {"paypal": {"usage_type": "MERCHANT", "email_address": "mock-buyer@example.test"}}}

    async def create_vaulted_order(self, purchase_unit: dict[str, Any], vault_id: str, request_id: str) -> dict[str, Any]:
        if not vault_id.startswith("MOCKVAULT"):
            raise PayPalError(422, {"name": "UNPROCESSABLE_ENTITY", "debug_id": "mock-debug",
                                    "message": "The vault_id does not match the payment_source provided.",
                                    "details": [{"issue": "INVALID_RESOURCE_ID"}]})
        if request_id in self.request_ids:
            return self.request_ids[request_id]
        order = await self.create_order(purchase_unit)
        response = order if not self.vault_completes_immediately else await self.capture_order(order["id"])
        self.request_ids[request_id] = response
        return response

    async def get_order(self, order_id: str) -> dict[str, Any]:
        order = self.orders.get(order_id)
        if order is None:
            raise PayPalError(404, {"name": "RESOURCE_NOT_FOUND", "details": [{"issue": "INVALID_RESOURCE_ID"}]})
        return {"id": order_id, "intent": "CAPTURE", "status": order["status"], "purchase_units": [order["purchase_unit"]]}

    async def capture_order(self, order_id: str) -> dict[str, Any]:
        order = self.orders.get(order_id)
        if order is None:
            raise PayPalError(404, {"name": "RESOURCE_NOT_FOUND", "details": [{"issue": "INVALID_RESOURCE_ID"}]})
        if self.scenario == "first_attempt_fails" and not self.transient_failure_sent:
            self.transient_failure_sent = True
            raise PayPalError(503, {"name": "SERVICE_UNAVAILABLE", "debug_id": "mock-debug",
                                    "message": "Service Unavailable."})
        if self.scenario == "capture_declined":
            raise PayPalError(422, {"name": "UNPROCESSABLE_ENTITY", "debug_id": "mock-debug",
                                    "message": "The instrument presented was declined.",
                                    "details": [{"issue": "INSTRUMENT_DECLINED"}]})
        amount = order["purchase_unit"]["amount"]
        gross = Decimal(amount["value"])
        if self.scenario == "capture_amount_mismatch":
            gross += Decimal("1.00")  # PayPal captured a different amount than the order
        fee = (gross * FEE_RATE + FEE_FIXED).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        net = gross - fee - (Decimal("0.50") if self.scenario == "fee_mismatch" else 0)
        order["status"] = "COMPLETED"
        money = lambda v: {"currency_code": amount["currency_code"], "value": v}  # noqa: E731
        capture_id = "MOCKCAP" + uuid.uuid4().hex[:10].upper()
        self.captures[capture_id] = money(_money(gross))
        self.transactions.append(_reporting_row(capture_id, "T0006", "S", money(_money(gross)), money(_money(-fee)),
                                                order_id, "ODR"))
        return {
            "id": order_id,
            "status": "COMPLETED",
            "purchase_units": [{
                "reference_id": order["purchase_unit"].get("reference_id"),
                "payments": {"captures": [{
                    "id": capture_id,
                    "status": "COMPLETED",
                    "amount": money(_money(gross)),
                    "final_capture": True,
                    "seller_receivable_breakdown": {
                        "gross_amount": money(_money(gross)),
                        "paypal_fee": money(_money(fee)),
                        "net_amount": money(_money(net)),
                    },
                }]},
            }],
        }

    async def refund_capture(self, capture_id: str) -> dict[str, Any]:
        amount = self.captures.get(capture_id)
        if amount is None:
            raise PayPalError(404, {"name": "RESOURCE_NOT_FOUND", "details": [{"issue": "INVALID_RESOURCE_ID"}]})
        refund = {"id": "MOCKREF" + uuid.uuid4().hex[:10].upper(), "status": "COMPLETED", "amount": dict(amount)}
        self.refunds[refund["id"]] = refund
        negative = {**amount, "value": _money(-Decimal(amount["value"]))}
        self.transactions.append(_reporting_row(refund["id"], "T1107", "S", negative, None, capture_id, "TXN"))
        return refund

    def sync_from_orders(self, orders: list[dict[str, Any]]) -> None:
        """Practice mode only: report captures this process did not make (the seed, the CLI, a server that
        restarted) from the stored orders. Only ids this mock issued (MOCKCAP...) are taken, so a sandbox
        order is never reported by the mock. Each needs capture id, gross, fee, time and currency."""
        known = {r["transaction_info"]["transaction_id"] for r in self.transactions}
        for o in orders:
            cid = o.get("capture_id") or ""
            if not cid.startswith("MOCKCAP") or cid in known or not (o.get("gross") and o.get("time")):
                continue
            money = lambda v: {"currency_code": o.get("currency") or "USD", "value": v}  # noqa: E731
            row = _reporting_row(cid, "T0006", "S", money(o["gross"]), money(_money(-abs(Decimal(o.get("fee") or "0")))),
                                 o.get("order_id") or "", "ODR")
            row["transaction_info"]["transaction_initiation_date"] = o["time"]
            self.transactions.append(row)
            known.add(cid)
            if o.get("refund"):
                self.transactions.append(_reporting_row(
                    "MOCKREF" + cid[7:], "T1107", "S", money(_money(-Decimal(o["refund"]))), None, cid, "TXN"))

    async def search_transactions(self, start: datetime, end: datetime, transaction_id: str | None = None) -> list[dict[str, Any]]:
        """Same shape as GET /v1/reporting/transactions with fields=all: transaction_details items."""
        self.searches.append((start, end, transaction_id))
        check_search_window(start, end)
        if self.search_error is not None:
            raise self.search_error
        if self.reporting_lag:
            return []
        found = []
        for row in self.transactions:
            info = dict(row["transaction_info"])
            when = datetime.fromisoformat(info["transaction_initiation_date"])
            if not start <= when <= end or (transaction_id and info["transaction_id"] != transaction_id):
                continue
            changes = self.report_overrides.get(info["transaction_id"], {})
            if "amount" in changes:
                info["transaction_amount"] = {**info["transaction_amount"], "value": changes["amount"]}
            if "fee" in changes:
                info["fee_amount"] = {**info["fee_amount"], "value": changes["fee"]}
            if "status" in changes:
                info["transaction_status"] = changes["status"]
            found.append({**row, "transaction_info": info})
        return found

    async def get_refund(self, refund_id: str) -> dict[str, Any]:
        refund = self.refunds.get(refund_id)
        if refund is None:
            raise PayPalError(404, {"name": "RESOURCE_NOT_FOUND", "details": [{"issue": "INVALID_RESOURCE_ID"}]})
        return refund


SDK_JS = r"""// MOCK PayPal v6 SDK (PAYPAL_MODE=mock). Not the real SDK; no PayPal servers involved.
(function () {
  var SCENARIO = __SCENARIO__;
  class PayPalButton extends HTMLElement {
    connectedCallback() {
      if (this.shadowRoot) return;
      var root = this.attachShadow({ mode: "open" });
      root.innerHTML = '<button type="button" style="width:100%;padding:12px;border:0;border-radius:4px;' +
        'background:#ffc439;font:bold 16px Arial,sans-serif;cursor:pointer">PayPal</button>';
    }
  }
  if (!customElements.get("paypal-button")) customElements.define("paypal-button", PayPalButton);

  // The other v6 buttons and the message, drawn like the real ones so a practice run sees the same elements.
  function simpleButton(label, background, color) {
    return class extends HTMLElement {
      connectedCallback() {
        if (this.shadowRoot) return;
        this.attachShadow({ mode: "open" }).innerHTML = '<button type="button" style="width:100%;padding:12px;margin-top:8px;' +
          'border:0;border-radius:4px;background:' + background + ';color:' + color +
          ';font:bold 16px Arial,sans-serif;cursor:pointer">' + label + '</button>';
      }
    };
  }
  [["venmo-button", "Venmo", "#008cff", "#fff"], ["paypal-pay-later-button", "Pay Later", "#ffc439", "#000"],
   ["paypal-basic-card-button", "Debit or Credit Card", "#2c2e2f", "#fff"]].forEach(function (b) {
    if (!customElements.get(b[0])) customElements.define(b[0], simpleButton(b[1], b[2], b[3]));
  });
  class PayPalMessage extends HTMLElement {
    setContent(content) {
      var amount = Number(this.dataset.amount || 0);
      this.textContent = "Pay in 4 interest-free payments of $" + (amount / 4).toFixed(2) + " with PayPal Pay Later.";
    }
  }
  if (!customElements.get("paypal-message")) customElements.define("paypal-message", PayPalMessage);

  window.paypal = {
    createInstance: async function (opts) {
      if (!opts || !opts.clientId) throw new Error("clientId is required");
      return {
        findEligibleMethods: async function () {
          return { isEligible: function (m) {
            return ["paypal", "venmo", "paylater", "card"].indexOf(m) >= 0 && SCENARIO !== "no_button";
          } };
        },
        createPayPalMessages: function () {
          return { fetchContent: async function () { return {}; } };
        },
        createVenmoOneTimePaymentSession: function (cb) { return oneTimeSession(cb); },
        createPayLaterOneTimePaymentSession: function (cb) { return oneTimeSession(cb); },
        createPayPalGuestOneTimePaymentSession: function (cb) { return oneTimeSession(cb); },
        createPayPalOneTimePaymentSession: function (cb) { return oneTimeSession(cb); },
      };
    },
  };

  function oneTimeSession(cb) {
    return {
      start: async function (options, orderPromise) {
        // Opened synchronously inside the click, like the real SDK, so it keeps transient activation.
        var popup = SCENARIO === "popup_blocked" ? null : window.open("about:blank", "mock-paypal", "width=480,height=640");
        if (!popup) {
          var err = new Error("Popup blocked by the browser");
          if (cb.onError) cb.onError(err);
          throw err;
        }
        var order;
        try { order = await orderPromise; } catch (e) { popup.close(); throw e; }
        popup.location.href = "/mock-paypal/checkout?token=" + encodeURIComponent(order.orderId);
        return new Promise(function (resolve) {
          window.addEventListener("message", async function handler(ev) {
            var d = ev.data || {};
            if (ev.origin !== location.origin || d.type !== "mock-paypal" || d.orderId !== order.orderId) return;
            window.removeEventListener("message", handler);
            if (d.action === "approve") await cb.onApprove({ orderId: order.orderId });
            else if (cb.onCancel) cb.onCancel({ orderId: order.orderId });
            resolve();
          });
        });
      },
    };
  }
})();
"""

POPUP_HTML = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>Log in to your PayPal account (MOCK)</title>
<style>body{{font-family:Arial,sans-serif;max-width:380px;margin:30px auto;padding:0 16px}}
input{{display:block;width:100%;padding:10px;margin:8px 0;box-sizing:border-box}}
button{{width:100%;padding:12px;margin-top:8px;border:0;border-radius:20px;background:#0070ba;color:#fff;font-size:15px}}
.step{{display:none}} .step.on{{display:block}} .note{{color:#a00;font-size:12px}}</style></head>
<body>
<p class="note">MOCK PayPal popup (PAYPAL_MODE=mock). Nothing is sent anywhere.</p>
<div id="step-captcha" class="step">
  <h1>Security check</h1>
  <div class="captcha-box"><label><input type="checkbox" id="captchaCheck"> I'm not a robot</label></div>
  <button id="captchaContinue" type="button">Continue</button>
</div>
<div id="step-email" class="step">
  <h1>Log in</h1>
  <input id="email" type="email" placeholder="Email or mobile number" autocomplete="off">
  <button id="btnNext" type="button">Next</button>
</div>
<div id="step-password" class="step">
  <input id="password" type="password" placeholder="Password" autocomplete="off">
  <button id="btnLogin" type="button">Log In</button>
</div>
<div id="step-verify" class="step">
  <h2>Verify it's you</h2>
  <p>We sent a code to your phone.</p>
  <input id="otpCode" type="text" inputmode="numeric" placeholder="6-digit code" autocomplete="off">
  <button id="btnVerify" type="button">Continue</button>
</div>
<div id="step-review" class="step">
  <h2>Pay Fernhill Ceramics</h2>
  <p>Total: <strong>{amount} {currency}</strong></p>
  {review_action}
  <a href="#" id="cancelLink">Cancel and return to store</a>
</div>
<script>
  var orderId = {order_id_json};
  var scenario = {scenario_json};
  function show(id) {{ document.querySelectorAll('.step').forEach(function (s) {{ s.classList.toggle('on', s.id === id); }}); }}
  function send(action) {{ window.opener.postMessage({{type: 'mock-paypal', action: action, orderId: orderId}}, location.origin); window.close(); }}
  show(scenario === 'captcha' ? 'step-captcha' : 'step-email');
  document.getElementById('captchaContinue').onclick = function () {{ if (document.getElementById('captchaCheck').checked) show('step-email'); }};
  document.getElementById('btnNext').onclick = function () {{ if (document.getElementById('email').value.trim()) show('step-password'); }};
  document.getElementById('btnLogin').onclick = function () {{
    var pw = document.getElementById('password');
    if (pw.value) {{ pw.value = ''; document.getElementById('email').value = '';
      if (scenario === 'buyer_cancels') {{ send('cancel'); return; }}
      if (scenario === 'seller_login') {{ location.href = '/mock-paypal/checkoutweb/genericError?code={error_code}'; return; }}
      show(scenario === 'verification_required' ? 'step-verify' : 'step-review'); }}
  }};
  document.getElementById('btnVerify').onclick = function () {{ if (/^\\d{{6}}$/.test(document.getElementById('otpCode').value)) show('step-review'); }};
  var pay = document.getElementById('payment-submit-btn');
  if (pay) pay.onclick = function () {{ send('approve'); }};
  document.getElementById('cancelLink').onclick = function (e) {{ e.preventDefault(); send('cancel'); }};
</script>
</body></html>"""


class ScenarioBody(BaseModel):
    scenario: Scenario


def mock_router(fake: FakePayPalClient) -> APIRouter:
    router = APIRouter(prefix="/mock-paypal", tags=["mock-paypal"], include_in_schema=False)

    @router.get("/sdk.js")
    def sdk_js():
        js = SDK_JS.replace("__SCENARIO__", json.dumps(fake.scenario))
        return Response(js, media_type="text/javascript", headers={"Cache-Control": "no-store"})

    @router.get("/checkout", response_class=HTMLResponse)
    def popup(token: str):
        order = fake.orders.get(token)
        if order is None:
            raise HTTPException(status_code=404, detail="Unknown mock order")
        amount = order["purchase_unit"]["amount"]
        if fake.scenario == "approval_stuck":
            action = '<p id="processing">Processing... please wait.</p>'
        else:
            action = '<button id="payment-submit-btn" type="button">Complete Purchase</button>'
        return POPUP_HTML.format(amount=html.escape(amount["value"]), currency=html.escape(amount["currency_code"]),
                                 review_action=action, order_id_json=json.dumps(token),
                                 scenario_json=json.dumps(fake.scenario), error_code=SELLER_LOGIN_ERROR_CODE)

    @router.get("/checkoutweb/genericError", response_class=HTMLResponse)
    def error_page():
        return ("<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\"><title>PayPal (MOCK)</title></head>"
                "<body><p>You are logging in to the account of the seller for this purchase. "
                "Please change your login information and try again.</p>"
                "<button type=\"button\">Log Out</button></body></html>")

    @router.get("/scenario")
    def get_scenario():
        return {"scenario": fake.scenario, "available": SCENARIOS}

    @router.put("/scenario")
    def set_scenario(body: ScenarioBody):
        fake.scenario = body.scenario
        fake.transient_failure_sent = False
        return {"scenario": fake.scenario}

    return router
