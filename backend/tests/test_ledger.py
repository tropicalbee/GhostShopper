import asyncio
import json
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from backend.app import db
from backend.app.main import create_app
from backend.app.owner import COOKIE, hash_token
from backend.app.paypal import SEARCH_PERMISSION_HINT, PayPalError
from backend.app.paypal_mock import FakePayPalClient
from backend.app.config import Settings
from store.app import ADMIN_COOKIE


@pytest.fixture
def fake():
    return FakePayPalClient()


@pytest.fixture
def client(tmp_path, fake):
    settings = Settings(paypal_client_id="", paypal_client_secret="", database_path=tmp_path / "test.db",
                        app_base_url="http://testserver", paypal_mode="mock")
    with TestClient(create_app(settings, paypal=fake)) as c:
        yield c


def db_path(client):
    return client.app.state.settings.database_path


def add_run(client, *, flaws=None, failed_stage=None, cause="store", checkout=1, status="completed", target="Speckled Stoneware Mug"):
    client.get("/api/health")  # makes sure this browser has its owner cookie
    owner = hash_token(client.cookies[COOKIE])
    with db.connect(db_path(client)) as conn:
        run_id = conn.execute(
            "INSERT INTO runs (started_at, finished_at, status, browser, store_url, goal, target_product, checkout,"
            " paypal_mode, llm, owner_hash, flaws_snapshot) VALUES ('2026-11-09T00:00:00+00:00',"
            " '2026-11-09T00:01:00+00:00', ?, 'local', 'http://x/store/', 'buy', ?, ?, ?, 'mock', ?, ?)",
            (status, target, checkout, client.app.state.settings.paypal_mode, owner,
             json.dumps(flaws if flaws is not None else {"price_in_image": True, "extra_step": False}))).lastrowid
        if failed_stage:
            conn.execute(
                "INSERT INTO checks (run_id, check_key, stage, passed, cause, severity, reason, created_at)"
                " VALUES (?, 'k', ?, 0, ?, 'high', 'x', '2026-11-09T00:00:30+00:00')", (run_id, failed_stage, cause))
    return run_id


def buy(client, run_id=None, refund=False):
    order_id = client.post("/api/paypal/orders", json={"sku": "FH-MUG-01"}).json()["id"]
    assert client.post(f"/api/paypal/orders/{order_id}/capture").status_code == 200
    if run_id:
        db.link_order_to_run(db_path(client), order_id, run_id)
        if refund:
            assert client.post(f"/api/paypal/orders/{order_id}/refund").status_code == 200
    return order_id


def ledger(client):
    r = client.get("/api/ledger")
    assert r.status_code == 200
    return r.json()


def by_order(body, order_id):
    return next(r for r in body["rows"] if r["order_id"] == order_id)


def test_row_kinds_and_totals(client):
    human = buy(client)
    agent = buy(client, add_run(client))
    risky = buy(client, add_run(client, failed_stage="checkout"))
    refunded = buy(client, add_run(client), refund=True)
    lost_run = add_run(client, failed_stage="payment")
    body = ledger(client)
    assert body["paypal_error"] is None
    assert (by_order(body, human)["source"], by_order(body, human)["store_state"]) == ("human", None)
    assert (by_order(body, agent)["source"], by_order(body, agent)["outcome"]) == ("agent", "captured")
    assert by_order(body, agent)["store_state"] == ["price_in_image"]
    assert by_order(body, risky)["outcome"] == "at_risk"
    row = by_order(body, refunded)
    assert (row["outcome"], row["refund"]) == ("refunded", "24.00")
    lost = next(r for r in body["rows"] if r["run_id"] == lost_run)
    assert (lost["outcome"], lost["stopped_at"], lost["amount_at_stake"], lost["capture_id"]) == ("lost", "payment", "24.00", None)
    assert len(body["rows"]) == 5
    t = body["totals"]
    assert t["lost"] == "24.00" and t["captured_gross"] == "96.00" and t["refunded"] == "24.00"
    assert t["fees"] == "5.32" and t["net"] == "90.68"  # 4 x (24.00 * 3.49% + 0.49 = 1.33)


def test_environment_failures_do_not_make_a_sale_at_risk(client):
    order = buy(client, add_run(client, failed_stage="payment", cause="environment"))
    assert by_order(ledger(client), order)["outcome"] == "captured"


def test_runs_without_checkout_or_still_running_are_not_lost_sales(client):
    add_run(client, checkout=0)
    add_run(client, status="running")
    assert ledger(client)["rows"] == []


def test_matched_in_paypal(client):
    order = buy(client, add_run(client))
    row = by_order(ledger(client), order)
    assert (row["paypal_reported"], row["paypal_status"]) == ("matched", "S")


def test_pending_when_paypal_has_not_caught_up(client, fake):
    order = buy(client, add_run(client))
    fake.reporting_lag = True
    row = by_order(ledger(client), order)
    assert (row["paypal_reported"], row["paypal_status"]) == ("pending", None)


def test_mismatch_on_amount_or_fee(client, fake):
    a, b = buy(client, add_run(client)), buy(client, add_run(client))
    body = ledger(client)
    fake.report_overrides[by_order(body, a)["capture_id"]] = {"amount": "25.00"}
    fake.report_overrides[by_order(body, b)["capture_id"]] = {"fee": "-2.00"}
    body = ledger(client)
    assert by_order(body, a)["paypal_reported"] == "mismatch"
    assert by_order(body, b)["paypal_reported"] == "mismatch"


def test_paypal_error_gives_not_checked_and_a_message(client, fake):
    order = buy(client, add_run(client))
    fake.search_error = PayPalError(403, {"name": "NOT_AUTHORIZED", "message": "Authorization failed. " + SEARCH_PERMISSION_HINT})
    body = ledger(client)
    assert by_order(body, order)["paypal_reported"] == "not_checked"
    assert "NOT_AUTHORIZED" in body["paypal_error"] and "Transaction search" in body["paypal_error"]


def test_search_window_is_at_most_31_days(client, fake):
    buy(client, add_run(client))
    ledger(client)
    start, end, _ = fake.searches[-1]
    assert timedelta(0) < end - start <= timedelta(days=31)


def test_old_captures_stay_not_checked(client, fake):
    order = buy(client, add_run(client))
    old = (datetime.now(timezone.utc) - timedelta(days=40)).isoformat()
    with db.connect(db_path(client)) as conn:
        conn.execute("UPDATE orders SET captured_at = ? WHERE order_id = ?", (old, order))
    body = ledger(client)
    assert by_order(body, order)["paypal_reported"] == "not_checked"
    assert fake.searches == []


def test_mock_search_refuses_a_long_window():
    asyncio.run(_refuses_long_window())


async def _refuses_long_window():
    now = datetime.now(timezone.utc)
    with pytest.raises(PayPalError) as exc:
        await FakePayPalClient().search_transactions(now - timedelta(days=32), now)
    assert exc.value.status_code == 400


def test_mock_search_shape_and_refund_row():
    asyncio.run(_search_shape())


async def _search_shape():
    fake = FakePayPalClient()
    order = await fake.create_order({"amount": {"currency_code": "USD", "value": "24.00"}})
    cap = (await fake.capture_order(order["id"]))["purchase_units"][0]["payments"]["captures"][0]
    await fake.refund_capture(cap["id"])
    now = datetime.now(timezone.utc)
    found = await fake.search_transactions(now - timedelta(days=1), now + timedelta(minutes=1))
    sale, refund = (t["transaction_info"] for t in found)
    assert sale["transaction_id"] == cap["id"] and sale["fee_amount"]["value"] == "-1.33"
    assert (refund["transaction_event_code"], refund["transaction_amount"]["value"], refund["paypal_reference_id"]) == ("T1107", "-24.00", cap["id"])
    assert len(await fake.search_transactions(now - timedelta(days=1), now + timedelta(minutes=1), cap["id"])) == 1


def test_other_browsers_runs_are_not_listed(client):
    run_id = add_run(client)
    with db.connect(db_path(client)) as conn:
        conn.execute("UPDATE runs SET owner_hash = 'someone-else' WHERE id = ?", (run_id,))
    assert ledger(client)["rows"] == []


def test_deployed_sandbox_rows_need_the_presenter_unlock(tmp_path):
    settings = Settings(paypal_client_id="id", paypal_client_secret="secret", database_path=tmp_path / "d.db",
                        app_base_url="https://shop.example.com", paypal_mode="sandbox", demo_admin_token="open-sesame")
    assert not settings.dev_options
    fake = FakePayPalClient()
    with TestClient(create_app(settings, paypal=fake), base_url="https://shop.example.com") as c:
        c.cookies.set(ADMIN_COOKIE, "open-sesame")
        order = buy(c, add_run(c))
        c.cookies.delete(ADMIN_COOKIE)
        body = ledger(c)
        assert by_order(body, order)["paypal_reported"] == "not_checked"
        assert "presenter unlock" in body["paypal_error"] and fake.searches == []
        c.cookies.set(ADMIN_COOKIE, "open-sesame")
        assert by_order(ledger(c), order)["paypal_reported"] == "matched"


def _real_client(handler):
    import httpx

    from backend.app.paypal import PayPalClient

    http = httpx.AsyncClient(base_url="https://api-m.sandbox.paypal.com", transport=httpx.MockTransport(handler))
    return PayPalClient("id", "secret", http=http)


def test_real_client_sends_documented_params_and_pages():
    import httpx

    seen = []

    def handler(request):
        if request.url.path == "/v1/oauth2/token":
            return httpx.Response(200, json={"access_token": "t", "expires_in": 3600})
        seen.append(dict(request.url.params))
        page = int(request.url.params["page"])
        return httpx.Response(200, json={"transaction_details": [{"transaction_info": {"transaction_id": f"T{page}"}}],
                                         "page": page, "total_pages": 2})

    now = datetime.now(timezone.utc)
    found = asyncio.run(_real_client(handler).search_transactions(now - timedelta(days=2), now, "CAP1"))
    assert [t["transaction_info"]["transaction_id"] for t in found] == ["T1", "T2"]
    assert seen[0]["fields"] == "all" and seen[0]["transaction_id"] == "CAP1" and seen[0]["start_date"].endswith("Z")
    assert [p["page"] for p in seen] == ["1", "2"]


def test_real_client_permission_error_carries_the_hint():
    import httpx

    def handler(request):
        if request.url.path == "/v1/oauth2/token":
            return httpx.Response(200, json={"access_token": "t", "expires_in": 3600})
        return httpx.Response(403, json={"name": "NOT_AUTHORIZED", "message": "Authorization failed due to insufficient permissions."})

    now = datetime.now(timezone.utc)
    with pytest.raises(PayPalError) as exc:
        asyncio.run(_real_client(handler).search_transactions(now - timedelta(days=1), now))
    assert exc.value.status_code == 403 and "Transaction search" in str(exc.value)
    with pytest.raises(PayPalError):  # refused before any request when over 31 days
        asyncio.run(_real_client(handler).search_transactions(now - timedelta(days=40), now))


def test_mock_capture_from_another_process_matches_after_a_restart(tmp_path):
    settings = Settings(paypal_client_id="", paypal_client_secret="", database_path=tmp_path / "r.db",
                        app_base_url="http://testserver", paypal_mode="mock")
    with TestClient(create_app(settings, paypal=FakePayPalClient())) as first:
        order = buy(first, add_run(first))
    # A new server process: a new fake client that never saw the capture.
    with TestClient(create_app(settings, paypal=FakePayPalClient())) as second:
        second.cookies.set(COOKIE, first.cookies[COOKIE])
        row = by_order(ledger(second), order)
        assert (row["paypal_reported"], row["paypal_mode"]) == ("matched", "mock")


def test_mock_never_reports_a_sandbox_order(client, fake):
    fake.sync_from_orders([{"capture_id": "5AB12345CD678901E", "gross": "24.00", "fee": "1.33", "time": "2026-11-09T00:00:00+00:00"}])
    assert fake.transactions == []
