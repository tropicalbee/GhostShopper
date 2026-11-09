"""Minimal PayPal Orders v2 client (sandbox only).

Docs: https://developer.paypal.com/api/rest/integration/orders-api/api-use-cases/standard
"""

import time
import uuid
from typing import Any

import httpx

from .config import PAYPAL_API_BASE


class PayPalError(Exception):
    """A non-2xx response from PayPal, with the fields needed to debug it."""

    def __init__(self, status_code: int, body: dict[str, Any]):
        self.status_code = status_code
        self.body = body
        self.name = body.get("name") or body.get("error") or "PAYPAL_ERROR"
        self.debug_id = body.get("debug_id")
        details = body.get("details") or []
        self.issue = details[0].get("issue") if details else None
        message = body.get("message") or body.get("error_description") or "PayPal request failed"
        super().__init__(f"{self.name}: {message}")


class PayPalClient:
    def __init__(self, client_id: str, client_secret: str, http: httpx.AsyncClient | None = None):
        self._client_id = client_id
        self._client_secret = client_secret
        self._http = http or httpx.AsyncClient(base_url=PAYPAL_API_BASE, timeout=30.0)
        self._token: str | None = None
        self._token_expires_at = 0.0

    async def aclose(self) -> None:
        await self._http.aclose()

    async def _access_token(self) -> str:
        # Refresh a minute early so a token never expires mid-request.
        if self._token and time.monotonic() < self._token_expires_at - 60:
            return self._token
        resp = await self._http.post(
            "/v1/oauth2/token",
            auth=(self._client_id, self._client_secret),
            data={"grant_type": "client_credentials"},
        )
        body = _json(resp)
        if resp.status_code != 200:
            raise PayPalError(resp.status_code, body)
        self._token = body["access_token"]
        self._token_expires_at = time.monotonic() + float(body.get("expires_in", 0))
        return self._token

    async def _post(self, path: str, payload: dict[str, Any], headers: dict[str, str]) -> dict[str, Any]:
        token = await self._access_token()
        resp = await self._http.post(
            path,
            json=payload,
            headers={"Authorization": f"Bearer {token}", **headers},
        )
        body = _json(resp)
        if resp.status_code not in (200, 201):
            raise PayPalError(resp.status_code, body)
        return body

    async def _get(self, path: str) -> dict[str, Any]:
        token = await self._access_token()
        resp = await self._http.get(path, headers={"Authorization": f"Bearer {token}"})
        body = _json(resp)
        if resp.status_code != 200:
            raise PayPalError(resp.status_code, body)
        return body

    async def create_order(self, purchase_unit: dict[str, Any]) -> dict[str, Any]:
        return await self._post(
            "/v2/checkout/orders",
            {"intent": "CAPTURE", "purchase_units": [purchase_unit]},
            # A fresh key per call: every call makes a new order. (Capture and refund use stable keys.)
            {"PayPal-Request-Id": str(uuid.uuid4())},
        )

    async def capture_order(self, order_id: str) -> dict[str, Any]:
        return await self._post(
            f"/v2/checkout/orders/{order_id}/capture",
            {},
            {"PayPal-Request-Id": f"capture-{order_id}", "Prefer": "return=representation"},
        )

    async def refund_capture(self, capture_id: str) -> dict[str, Any]:
        # An empty body refunds the full captured amount. The key makes a retried refund return the same one.
        return await self._post(
            f"/v2/payments/captures/{capture_id}/refund",
            {},
            {"PayPal-Request-Id": f"refund-{capture_id}", "Prefer": "return=representation"},
        )

    # Vault v3 (save a PayPal account without a purchase), then pay with the saved token.
    # Docs: https://developer.paypal.com/docs/checkout/save-payment-methods/purchase-later/js-sdk/paypal/
    #       https://developer.paypal.com/docs/api/payment-tokens/v3/

    async def create_setup_token(self, return_url: str, cancel_url: str) -> dict[str, Any]:
        """POST /v3/vault/setup-tokens. The response has the setup token id and an `approve` link for the buyer."""
        return await self._post(
            "/v3/vault/setup-tokens",
            {"payment_source": {"paypal": {"usage_type": "MERCHANT",
                                           "experience_context": {"return_url": return_url, "cancel_url": cancel_url}}}},
            {"PayPal-Request-Id": str(uuid.uuid4())},
        )

    async def create_payment_token(self, setup_token_id: str) -> dict[str, Any]:
        """POST /v3/vault/payment-tokens: exchange an approved setup token. The response has `id` and `customer.id`."""
        return await self._post(
            "/v3/vault/payment-tokens",
            {"payment_source": {"token": {"id": setup_token_id, "type": "SETUP_TOKEN"}}},
            {"PayPal-Request-Id": f"vault-{setup_token_id}"},
        )

    async def create_vaulted_order(self, purchase_unit: dict[str, Any], vault_id: str, request_id: str) -> dict[str, Any]:
        """POST /v2/checkout/orders with payment_source.paypal.vault_id. No buyer approval step is needed; PayPal
        may answer COMPLETED straight away, otherwise the caller captures. request_id makes a retry return the
        same order instead of charging twice."""
        return await self._post(
            "/v2/checkout/orders",
            {"intent": "CAPTURE", "purchase_units": [purchase_unit],
             "payment_source": {"paypal": {"vault_id": vault_id}}},
            {"PayPal-Request-Id": request_id, "Prefer": "return=representation"},
        )

    async def get_refund(self, refund_id: str) -> dict[str, Any]:
        return await self._get(f"/v2/payments/refunds/{refund_id}")


def _json(resp: httpx.Response) -> dict[str, Any]:
    try:
        body = resp.json()
    except ValueError:
        return {"message": resp.text[:500]}
    return body if isinstance(body, dict) else {"message": str(body)}


def summarize_capture(order: dict[str, Any]) -> dict[str, Any]:
    """Pull the capture id, status and seller fee breakdown out of a capture response."""
    capture = order["purchase_units"][0]["payments"]["captures"][0]
    breakdown = capture.get("seller_receivable_breakdown") or {}

    def value(key: str) -> str | None:
        return (breakdown.get(key) or {}).get("value")

    return {
        "order_id": order["id"],
        "order_status": order["status"],
        "capture_id": capture["id"],
        "capture_status": capture["status"],
        "currency": capture["amount"]["currency_code"],
        "gross_amount": value("gross_amount") or capture["amount"]["value"],
        "paypal_fee": value("paypal_fee"),
        "net_amount": value("net_amount"),
    }
