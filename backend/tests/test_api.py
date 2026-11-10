from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.app import db
from backend.app.config import Settings
from backend.app.main import create_app
from backend.app.paypal import PayPalError, summarize_capture


def capture_response(order_id: str, value: str) -> dict:
    return {
        "id": order_id,
        "status": "COMPLETED",
        "purchase_units": [
            {
                "payments": {
                    "captures": [
                        {
                            "id": "CAP123",
                            "status": "COMPLETED",
                            "amount": {"currency_code": "USD", "value": value},
                            "seller_receivable_breakdown": {
                                "gross_amount": {"currency_code": "USD", "value": value},
                                "paypal_fee": {"currency_code": "USD", "value": "1.33"},
                                "net_amount": {"currency_code": "USD", "value": "22.67"},
                            },
                        }
                    ]
                }
            }
        ],
    }


class FakePayPal:
    def __init__(self):
        self.created: list[dict] = []
        self.fail_capture: PayPalError | None = None

    async def create_order(self, purchase_unit):
        self.created.append(purchase_unit)
        return {"id": "ORDER123ABC", "status": "CREATED"}

    async def get_order(self, order_id):
        return {"id": order_id, "status": "CREATED", "purchase_units": [self.created[-1]]}

    async def capture_order(self, order_id):
        if self.fail_capture:
            raise self.fail_capture
        return capture_response(order_id, self.created[-1]["amount"]["value"])


def make_settings(tmp_path: Path, configured: bool = True) -> Settings:
    return Settings(
        paypal_client_id="test-client" if configured else "",
        paypal_client_secret="test-secret" if configured else "",
        database_path=tmp_path / "test.db",
        app_base_url="http://testserver",
    )


@pytest.fixture
def fake():
    return FakePayPal()


@pytest.fixture
def client(tmp_path, fake):
    with TestClient(create_app(make_settings(tmp_path), paypal=fake)) as c:
        yield c


def test_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert {k: body[k] for k in ("status", "paypal_configured", "paypal_env")} == {
        "status": "ok", "paypal_configured": True, "paypal_env": "sandbox"}
    assert isinstance(body["groq_configured"], bool)


def test_create_order_prices_from_catalog(client, fake):
    r = client.post("/api/paypal/orders", json={"sku": "FH-MUG-01", "quantity": 2})
    assert r.status_code == 201
    assert r.json() == {
        "id": "ORDER123ABC", "status": "CREATED", "amount": "48.00", "currency": "USD", "store_order": 1042}
    unit = fake.created[0]
    assert unit["amount"]["value"] == "48.00"
    assert unit["amount"]["breakdown"]["item_total"]["value"] == "48.00"
    assert unit["items"][0] == {
        "name": "Speckled Stoneware Mug",
        "sku": "FH-MUG-01",
        "quantity": "2",
        "category": "PHYSICAL_GOODS",
        "unit_amount": {"currency_code": "USD", "value": "24.00"},
    }


def test_create_order_ignores_client_price(client, fake):
    r = client.post("/api/paypal/orders", json={"sku": "FH-MUG-01", "quantity": 1, "price": "0.01"})
    assert r.status_code == 201
    assert fake.created[0]["amount"]["value"] == "24.00"


@pytest.mark.parametrize(
    "payload,status",
    [
        ({"sku": "NOPE"}, 404),
        ({"sku": "FH-ESP-04"}, 409),  # out of stock
        ({"sku": "FH-MUG-01", "quantity": 0}, 422),
        ({"sku": "FH-MUG-01", "quantity": 11}, 422),
    ],
)
def test_create_order_rejects_bad_input(client, payload, status):
    assert client.post("/api/paypal/orders", json=payload).status_code == status


def test_capture_records_fees(client, tmp_path):
    client.post("/api/paypal/orders", json={"sku": "FH-MUG-01"})
    r = client.post("/api/paypal/orders/ORDER123ABC/capture")
    assert r.status_code == 200
    assert r.json() == {
        "order_id": "ORDER123ABC",
        "order_status": "COMPLETED",
        "capture_id": "CAP123",
        "capture_status": "COMPLETED",
        "currency": "USD",
        "gross_amount": "24.00",
        "paypal_fee": "1.33",
        "net_amount": "22.67",
        "store_order": 1042,
    }
    stored = db.get_order(tmp_path / "test.db", "ORDER123ABC")
    assert stored["status"] == "COMPLETED"
    assert stored["capture_id"] == "CAP123"
    assert stored["paypal_fee"] == "1.33"
    assert client.get("/api/paypal/orders/ORDER123ABC").json()["net_amount"] == "22.67"


def test_capture_unknown_or_malformed_order(client):
    assert client.post("/api/paypal/orders/NEVERCREATED1/capture").status_code == 404
    assert client.post("/api/paypal/orders/bad..id/capture").status_code == 400


def test_capture_passes_through_paypal_decline(client, fake):
    client.post("/api/paypal/orders", json={"sku": "FH-MUG-01"})
    fake.fail_capture = PayPalError(
        422,
        {"name": "UNPROCESSABLE_ENTITY", "debug_id": "dbg1", "details": [{"issue": "INSTRUMENT_DECLINED"}]},
    )
    r = client.post("/api/paypal/orders/ORDER123ABC/capture")
    assert r.status_code == 422
    assert r.json()["detail"]["issue"] == "INSTRUMENT_DECLINED"
    assert r.json()["detail"]["debug_id"] == "dbg1"


def test_unconfigured_paypal_is_an_explicit_error(tmp_path):
    with TestClient(create_app(make_settings(tmp_path, configured=False))) as c:
        assert c.get("/api/health").json()["paypal_configured"] is False
        r = c.post("/api/paypal/orders", json={"sku": "FH-MUG-01"})
        assert r.status_code == 503
        assert r.json()["detail"]["error"] == "PAYPAL_NOT_CONFIGURED"


def test_summarize_capture_without_breakdown():
    resp = capture_response("O1", "10.00")
    del resp["purchase_units"][0]["payments"]["captures"][0]["seller_receivable_breakdown"]
    summary = summarize_capture(resp)
    assert summary["gross_amount"] == "10.00"
    assert summary["paypal_fee"] is None
