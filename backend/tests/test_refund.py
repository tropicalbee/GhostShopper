import pytest
from fastapi.testclient import TestClient

from backend.app import db
from backend.app.main import create_app
from backend.app.owner import COOKIE, hash_token
from backend.app.paypal import PayPalError
from backend.app.paypal_mock import FakePayPalClient

from .test_api import make_settings


class WrongAmountPayPal(FakePayPalClient):
    """PayPal reports a smaller refund than the payment."""

    async def get_refund(self, refund_id):
        refund = dict(await super().get_refund(refund_id))
        refund["amount"] = {**refund["amount"], "value": "10.00"}
        return refund


@pytest.fixture
def fake():
    return FakePayPalClient()


@pytest.fixture
def client(tmp_path, fake):
    with TestClient(create_app(make_settings(tmp_path), paypal=fake)) as c:
        yield c


def place_order(client, capture: bool = True, owner: str | None = "self") -> str:
    """An order linked to a run owned by this client's browser (owner="self"), a shared example (None),
    or another browser (any other hash)."""
    order_id = client.post("/api/paypal/orders", json={"sku": "FH-MUG-01"}).json()["id"]
    if capture:
        assert client.post(f"/api/paypal/orders/{order_id}/capture").status_code == 200
    if owner == "self":
        owner = hash_token(client.cookies[COOKIE])
    db_path = client.app.state.settings.database_path
    with db.connect(db_path) as conn:
        run_id = conn.execute(
            "INSERT INTO runs (started_at, status, browser, store_url, goal, target_product, checkout, paypal_mode,"
            " llm, owner_hash) VALUES ('2026-11-07T00:00:00+00:00', 'completed', 'local', 'http://x/store/',"
            " 'buy', 'FH-MUG-01', 1, 'mock', 'mock', ?)", (owner,)).lastrowid
    db.link_order_to_run(db_path, order_id, run_id)
    return order_id


def test_refund_is_verified_and_stored(client, tmp_path):
    order_id = place_order(client)
    r = client.post(f"/api/paypal/orders/{order_id}/refund")
    assert r.status_code == 200
    body = r.json()
    assert body["order_id"] == order_id
    assert body["status"] == "COMPLETED"
    assert (body["amount"], body["currency"]) == ("24.00", "USD")
    assert body["verified"] is True and body["mismatches"] == []
    stored = db.get_order(tmp_path / "test.db", order_id)
    assert stored["refund_id"] == body["refund_id"]
    assert stored["refund_status"] == "COMPLETED"
    assert stored["refunded_at"]
    assert client.get(f"/api/paypal/orders/{order_id}").json()["refund_amount"] == "24.00"


def test_second_refund_is_refused(client):
    order_id = place_order(client)
    assert client.post(f"/api/paypal/orders/{order_id}/refund").status_code == 200
    r = client.post(f"/api/paypal/orders/{order_id}/refund")
    assert r.status_code == 409
    assert r.json()["detail"]["error"] == "ALREADY_REFUNDED"


def test_uncaptured_order_cannot_be_refunded(client):
    order_id = place_order(client, capture=False)
    r = client.post(f"/api/paypal/orders/{order_id}/refund")
    assert r.status_code == 409
    assert r.json()["detail"]["error"] == "NOT_CAPTURED"


def test_unknown_order(client):
    assert client.post("/api/paypal/orders/NEVERCREATED1/refund").status_code == 404
    assert client.post("/api/paypal/orders/bad..id/refund").status_code == 400


@pytest.mark.parametrize("owner", [None, "0" * 64])
def test_only_the_owning_browser_can_refund(client, owner):
    # Shared examples (None) and other browsers' orders look unknown, like their runs do.
    order_id = place_order(client, owner=owner)
    r = client.post(f"/api/paypal/orders/{order_id}/refund")
    assert r.status_code == 404
    assert r.json()["detail"]["error"] == "UNKNOWN_ORDER"


def test_refund_amount_mismatch_is_reported(tmp_path):
    with TestClient(create_app(make_settings(tmp_path), paypal=WrongAmountPayPal())) as c:
        order_id = place_order(c)
        body = c.post(f"/api/paypal/orders/{order_id}/refund").json()
    assert body["verified"] is False
    assert body["mismatches"] == ["Refunded 10.00, but 24.00 was captured"]


def test_paypal_refund_error_is_passed_through(client, fake, tmp_path):
    order_id = place_order(client)

    async def declined(capture_id):
        raise PayPalError(422, {"name": "UNPROCESSABLE_ENTITY", "details": [{"issue": "CAPTURE_FULLY_REFUNDED"}]})

    fake.refund_capture = declined
    r = client.post(f"/api/paypal/orders/{order_id}/refund")
    assert r.status_code == 422
    assert r.json()["detail"]["issue"] == "CAPTURE_FULLY_REFUNDED"
    assert db.get_order(tmp_path / "test.db", order_id)["refund_id"] is None


def test_run_payload_carries_order_times_and_the_refund_after_it_happens(client):
    order_id = place_order(client)
    with db.connect(client.app.state.settings.database_path) as conn:
        run_id = conn.execute("SELECT run_id FROM orders WHERE order_id = ?", (order_id,)).fetchone()[0]
    before = client.get(f"/api/runs/{run_id}").json()["order"]  # also fills the finished-run cache
    assert before["created_at"] and before["captured_at"] and before["refunded_at"] is None
    assert before["refund_id"] is None
    body = client.post(f"/api/paypal/orders/{order_id}/refund").json()
    after = client.get(f"/api/runs/{run_id}").json()["order"]
    assert after["refund_id"] == body["refund_id"] and after["refunded_at"] == body["refunded_at"]
