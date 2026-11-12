import httpx
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
            " 'buy', 'FH-MUG-01', 1, ?, 'mock', ?)",
            (client.app.state.settings.paypal_mode, owner)).lastrowid  # the mode the injected fake is registered under
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
    assert client.get(f"/api/paypal/orders/{order_id}", headers={"X-GhostShopper-Key": client.app.state.internal_key}).json()["refund_amount"] == "24.00"


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


def test_reading_an_order_validates_the_id(client):
    assert client.get("/api/paypal/orders/bad..id", headers={"X-GhostShopper-Key": client.app.state.internal_key}).status_code == 400
    assert client.get("/api/paypal/orders/bad..id/verify", headers={"X-GhostShopper-Key": client.app.state.internal_key}).status_code == 400
    assert client.get("/api/paypal/orders/NEVERCREATED1/verify", headers={"X-GhostShopper-Key": client.app.state.internal_key}).status_code == 404


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


def test_http_error_from_paypal_is_a_502_and_nothing_is_stored(client, fake, tmp_path):
    order_id = place_order(client)

    async def down(capture_id):
        raise httpx.ConnectError("boom")

    fake.refund_capture = down
    r = client.post(f"/api/paypal/orders/{order_id}/refund")
    assert r.status_code == 502
    assert r.json()["detail"]["error"] == "PAYPAL_UNREACHABLE"
    assert db.get_order(tmp_path / "test.db", order_id)["refund_id"] is None


def test_failed_read_back_keeps_the_issued_refund_and_a_retry_completes_it(client, fake, tmp_path):
    order_id = place_order(client)
    real, real_refund = fake.get_refund, fake.refund_capture
    calls = []

    async def partial(capture_id):  # PayPal answered the refund with just an id and a pending status
        issued = await real_refund(capture_id)
        return {"id": issued["id"], "status": "PENDING"}

    fake.refund_capture = partial

    async def flaky(refund_id):
        calls.append(refund_id)
        if len(calls) == 1:
            raise httpx.ReadTimeout("slow")
        return await real(refund_id)

    fake.get_refund = flaky
    r = client.post(f"/api/paypal/orders/{order_id}/refund")
    assert r.status_code == 502 and "was issued" in r.json()["detail"]["message"]
    kept = db.get_order(tmp_path / "test.db", order_id)
    assert kept["refund_id"] == calls[0] and kept["refund_status"] == "PENDING"
    r = client.post(f"/api/paypal/orders/{order_id}/refund")  # not ALREADY_REFUNDED: it only reads the refund again
    assert r.status_code == 200 and r.json()["refund_id"] == calls[0] and r.json()["verified"] is True
    assert db.get_order(tmp_path / "test.db", order_id)["refund_amount"] == "24.00"
    assert client.post(f"/api/paypal/orders/{order_id}/refund").status_code == 409


def test_malformed_refund_body_is_a_502(client, fake):
    order_id = place_order(client)

    async def bad(refund_id):
        return {"id": refund_id}

    fake.get_refund = bad
    r = client.post(f"/api/paypal/orders/{order_id}/refund")
    assert r.status_code == 502 and r.json()["detail"]["error"] == "PAYPAL_BAD_RESPONSE"


def test_record_refund_never_overwrites_another_refund(client, tmp_path):
    order_id = place_order(client)
    path = tmp_path / "test.db"
    amount = {"value": "24.00", "currency_code": "USD"}
    db.record_refund(path, order_id, {"id": "R1", "status": "COMPLETED", "amount": amount})
    db.record_refund(path, order_id, {"id": "R2", "status": "PENDING", "amount": amount})
    assert db.get_order(path, order_id)["refund_id"] == "R1"
    assert db.get_order(path, order_id)["refund_status"] == "COMPLETED"


def test_order_reads_are_agent_only(client):
    order_id = place_order(client)
    for path in (f"/api/paypal/orders/{order_id}", f"/api/paypal/orders/{order_id}/verify"):
        assert client.get(path).status_code == 404
        assert client.get(path, headers={"X-GhostShopper-Key": "wrong"}).status_code == 404
        assert client.get(path, headers={"X-GhostShopper-Key": client.app.state.internal_key}).status_code == 200
    assert "UNKNOWN_ORDER" in client.get(f"/api/paypal/orders/{order_id}").text


def test_server_writes_its_key_file_at_startup(client):
    key_file = client.app.state.settings.database_path.parent / ".internal_key"
    assert key_file.read_text(encoding="utf-8") == client.app.state.internal_key
