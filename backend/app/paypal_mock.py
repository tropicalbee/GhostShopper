"""PAYPAL_MODE=mock: a fake Orders v2 client plus a mock v6 JS SDK and popup.

No PayPal servers are contacted. The popup imitates the sandbox login/approve pages (same element ids)
so the agent's PayPal flow runs unchanged. Scenarios simulate the checkout failures the score checks for.
"""

import base64
import html
import json
import uuid
from decimal import ROUND_HALF_UP, Decimal
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, Response
from pydantic import BaseModel

from .paypal import PayPalError

MOCK_CLIENT_ID = "mock-client-id"
MOCK_SDK_PATH = "/mock-paypal/sdk.js"
SCENARIOS = ("ok", "no_button", "popup_blocked", "approval_stuck", "capture_declined",
             "captcha", "verification_required", "capture_amount_mismatch", "fee_mismatch", "seller_login")
Scenario = Literal["ok", "no_button", "popup_blocked", "approval_stuck", "capture_declined",
                   "captcha", "verification_required", "capture_amount_mismatch", "fee_mismatch", "seller_login"]
# seller_login: the buyer logs in with the seller's account and PayPal answers with its error page.
SELLER_LOGIN_ERROR_CODE = base64.urlsafe_b64encode(b"CANNOT_PAY_SELF").decode().rstrip("=")

# PayPal US standard checkout rate, used only to make fake fee numbers realistic.
FEE_RATE = Decimal("0.0349")
FEE_FIXED = Decimal("0.49")


def _money(d: Decimal) -> str:
    return str(d.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


class FakePayPalClient:
    """Same interface as PayPalClient. Keeps orders in memory."""

    def __init__(self):
        self.orders: dict[str, dict[str, Any]] = {}
        self.scenario: str = "ok"
        self.captures: dict[str, dict[str, str]] = {}  # capture id -> amount, so a refund can return it
        self.refunds: dict[str, dict[str, Any]] = {}

    async def aclose(self) -> None:
        pass

    async def create_order(self, purchase_unit: dict[str, Any]) -> dict[str, Any]:
        order_id = "MOCK" + uuid.uuid4().hex[:13].upper()
        self.orders[order_id] = {"purchase_unit": purchase_unit, "status": "CREATED"}
        return {"id": order_id, "status": "CREATED"}

    async def capture_order(self, order_id: str) -> dict[str, Any]:
        order = self.orders.get(order_id)
        if order is None:
            raise PayPalError(404, {"name": "RESOURCE_NOT_FOUND", "details": [{"issue": "INVALID_RESOURCE_ID"}]})
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
        return refund

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

  window.paypal = {
    createInstance: async function (opts) {
      if (!opts || !opts.clientId) throw new Error("clientId is required");
      return {
        findEligibleMethods: async function () {
          return { isEligible: function (m) { return m === "paypal" && SCENARIO !== "no_button"; } };
        },
        createPayPalOneTimePaymentSession: function (cb) {
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
        },
      };
    },
  };
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
        return {"scenario": fake.scenario}

    return router
