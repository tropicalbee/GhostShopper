"""The store's own orders over the API: every payment path creates them, and the four purchase flaws change them."""

import pytest
from fastapi.testclient import TestClient

from backend.app.config import Settings
from backend.app.main import create_app
from backend.app.paypal_mock import FakePayPalClient

SKU = "FH-MUG-01"


@pytest.fixture
def client(tmp_path):
    settings = Settings(paypal_client_id="", paypal_client_secret="", database_path=tmp_path / "so.db",
                        app_base_url="http://localhost:8000", paypal_mode="mock", dev_options=True)
    fake = FakePayPalClient()
    with TestClient(create_app(settings, paypal=fake)) as c:
        c.fake = fake
        yield c


def flaw(client, key):
    client.put("/store/admin/flaws.json", json={"flaws": {key: True}}).raise_for_status()


def place(client, store_order=None) -> dict:
    r = client.post("/api/paypal/orders", json={"sku": SKU, "quantity": 1, "store_order": store_order})
    assert r.status_code == 201, r.text
    return r.json()


def order_page_status(client, number) -> str:
    text = client.get(f"/store/orders/{number}").text
    return text.split('id="order-status">')[1].split("<")[0]


def test_a_paid_order_is_marked_paid_on_the_order_page(client):
    order = place(client)
    assert order["store_order"] == 1042 and order_page_status(client, 1042) == "Awaiting payment"
    captured = client.post(f"/api/paypal/orders/{order['id']}/capture").json()
    assert captured["store_order"] == 1042
    assert order_page_status(client, 1042) == "Paid"
    paypal = client.fake.orders[order["id"]]
    assert paypal["status"] == "COMPLETED"


def test_paypal_orders_are_read_back_for_the_trace(client):
    order = place(client)
    client.post(f"/api/paypal/orders/{order['id']}/capture")
    from backend.app import db

    stored = db.get_order(client.app.state.settings.database_path, order["id"], include_raw=True)
    assert '"items"' in stored["order_response"] and stored["capture_error"] is None


def test_never_marks_paid_leaves_a_captured_order_awaiting_payment(client):
    flaw(client, "never_marks_paid")
    order = place(client)
    assert client.post(f"/api/paypal/orders/{order['id']}/capture").status_code == 200
    assert client.fake.orders[order["id"]]["status"] == "COMPLETED"
    assert order_page_status(client, 1042) == "Awaiting payment"


def test_declined_payment_fails_the_order_and_tells_the_buyer(client):
    client.fake.scenario = "capture_declined"
    order = place(client)
    r = client.post(f"/api/paypal/orders/{order['id']}/capture")
    assert r.status_code == 422 and r.json()["detail"]["issue"] == "INSTRUMENT_DECLINED"
    assert order_page_status(client, 1042) == "Payment failed"


def test_declined_marked_paid_shows_success_without_a_capture(client):
    flaw(client, "declined_marked_paid")
    client.fake.scenario = "capture_declined"
    order = place(client)
    r = client.post(f"/api/paypal/orders/{order['id']}/capture")
    assert r.status_code == 200 and r.json() == {"order_id": order["id"], "capture_id": None, "store_order": 1042}
    assert order_page_status(client, 1042) == "Paid"


def test_a_cancelled_payment_cancels_the_order(client):
    order = place(client)
    r = client.post(f"/api/paypal/orders/{order['id']}/cancel")
    assert r.json() == {"store_order": 1042, "status": "cancelled"}
    assert order_page_status(client, 1042) == "Cancelled"
    assert client.post(f"/api/paypal/orders/{order['id']}/cancel").json()["status"] == "cancelled"


def test_success_after_cancel_confirms_the_order(client):
    flaw(client, "success_after_cancel")
    order = place(client)
    assert client.post(f"/api/paypal/orders/{order['id']}/cancel").json() == {"store_order": 1042, "status": "confirmed"}
    assert order_page_status(client, 1042) == "Confirmed"


def test_cancelling_an_unknown_or_malformed_order(client):
    assert client.post("/api/paypal/orders/NEVERCREATED1/cancel").status_code == 404
    assert client.post("/api/paypal/orders/bad..id/cancel").status_code == 400


def test_a_retry_after_a_temporary_failure_reuses_the_pending_order(client):
    client.fake.scenario = "first_attempt_fails"
    first = place(client)
    failed = client.post(f"/api/paypal/orders/{first['id']}/capture")
    assert failed.status_code == 502 and failed.json()["detail"]["error"] == "SERVICE_UNAVAILABLE"
    assert order_page_status(client, 1042) == "Awaiting payment"
    second = place(client, store_order=first["store_order"])
    assert second["store_order"] == 1042 and second["id"] != first["id"]
    assert client.post(f"/api/paypal/orders/{second['id']}/capture").status_code == 200
    assert order_page_status(client, 1042) == "Paid"
    assert client.get("/store/orders/1043").status_code == 404


def test_duplicate_on_retry_creates_a_second_order(client):
    flaw(client, "duplicate_on_retry")
    client.fake.scenario = "first_attempt_fails"
    first = place(client)
    client.post(f"/api/paypal/orders/{first['id']}/capture")
    second = place(client, store_order=first["store_order"])
    assert second["store_order"] == 1043
    client.post(f"/api/paypal/orders/{second['id']}/capture")
    assert (order_page_status(client, 1042), order_page_status(client, 1043)) == ("Awaiting payment", "Paid")


VAULT = {"sku": SKU, "quantity": 1, "vault_id": "MOCKVAULTABC123", "request_id": "req-0001-abcd"}


def test_the_agent_payment_creates_and_settles_a_store_order_too(client):
    r = client.post("/api/paypal/agent-orders", json=VAULT)
    assert r.status_code == 201 and r.json()["store_order"] == 1042
    assert order_page_status(client, 1042) == "Paid"
    again = client.post("/api/paypal/agent-orders", json=VAULT)  # same request id: same PayPal order, same store order
    assert again.json()["store_order"] == 1042


def test_the_agent_payment_follows_the_same_flaws(client):
    flaw(client, "never_marks_paid")
    assert client.post("/api/paypal/agent-orders", json=VAULT).status_code == 201
    assert order_page_status(client, 1042) == "Awaiting payment"


def test_a_declined_agent_payment_names_its_store_order(client):
    client.fake.scenario = "capture_declined"
    r = client.post("/api/paypal/agent-orders", json=VAULT)
    assert r.status_code == 422 and r.json()["detail"]["store_order"] == 1042
    assert order_page_status(client, 1042) == "Payment failed"
    flaw(client, "declined_marked_paid")
    r = client.post("/api/paypal/agent-orders", json={**VAULT, "request_id": "req-0002-abcd"})
    assert r.status_code == 422 and order_page_status(client, r.json()["detail"]["store_order"]) == "Paid"
