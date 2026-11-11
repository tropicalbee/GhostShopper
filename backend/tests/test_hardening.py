"""Abuse limits before a public deploy: spoofed X-Forwarded-For, daily caps, the mock PayPal switch, capped and
pinned server-side fetches, the admin unlock, and a bad spending limit."""

from types import SimpleNamespace

import httpx
import pytest
from fastapi.testclient import TestClient

from backend.app import runs
from backend.app.agent import site
from backend.app.agent.site import PinnedTransport, Politeness, SiteError, preflight, resolve_checked
from backend.app.config import Settings
from backend.app.main import create_app
from backend.app.paypal_mock import FakePayPalClient
from store.app import ADMIN_COOKIE, admin_cookie_value

TOKEN = "t0ken-for-the-presenter"


def settings(tmp_path, **kw) -> Settings:
    return Settings("", "", tmp_path / "h.db", "https://ghostshopper.example", runs_dir=tmp_path / "runs",
                    frontend_dist=tmp_path / "dist", **kw)


def start(app, forwarded: str | None = None, admin: bool = False):
    """One start request from a brand new browser (no owner cookie), as an attacker rotating cookies would send."""
    c = TestClient(app, base_url="https://testserver")
    if admin:
        c.cookies.set(ADMIN_COOKIE, admin_cookie_value(TOKEN))
    headers = {"X-Forwarded-For": forwarded} if forwarded else {}
    return c.post("/api/runs", json={"store_url": "not a url"}, headers=headers)


# --- Rate limits key on the proxy-written X-Forwarded-For entry ---

def test_a_spoofed_leftmost_forwarded_address_does_not_dodge_the_limit(tmp_path):
    app = create_app(settings(tmp_path, run_rate_limit=(3, 600)))
    codes = [start(app, f"10.0.0.{i}, 203.0.113.7").status_code for i in range(5)]  # real hop: 203.0.113.7
    assert codes == [400, 400, 400, 429, 429]
    assert start(app, "10.0.0.1, 198.51.100.9").status_code == 400  # another real client is unaffected


def test_trusted_proxy_hops_picks_the_entry_from_the_right(tmp_path):
    app = create_app(settings(tmp_path, run_rate_limit=(1, 600), trusted_proxy_hops=2))
    assert start(app, "1.1.1.1, 203.0.113.7, 10.9.9.9").status_code == 400
    assert start(app, "2.2.2.2, 203.0.113.7, 10.8.8.8").status_code == 429  # same entry two from the right


def test_no_forwarded_header_falls_back_to_the_socket_peer(tmp_path):
    app = create_app(settings(tmp_path, run_rate_limit=(1, 600)))
    assert [start(app).status_code for _ in range(2)] == [400, 429]


def valid_start(app, monkeypatch, forwarded: str, admin: bool = False):
    """A start that passes validation (the run itself is replaced), from a brand new browser."""
    async def fake_execute(req, url, db_path, on_start=None, **kw):
        on_start(1)

    monkeypatch.setattr(runs, "execute", fake_execute)
    monkeypatch.setattr(runs, "prepare", lambda *a, **k: (None, None))
    c = TestClient(app, base_url="https://testserver")
    if admin:
        c.cookies.set(ADMIN_COOKIE, admin_cookie_value(TOKEN))
    return c.post("/api/runs", json={}, headers={"X-Forwarded-For": forwarded})


def test_daily_caps_are_global_and_the_presenter_skips_them(tmp_path, monkeypatch):
    app = create_app(settings(tmp_path, run_daily_cap=2, run_rate_limit=(50, 600), demo_admin_token=TOKEN))
    assert [valid_start(app, monkeypatch, f"198.51.100.{i}").status_code for i in range(2)] == [202, 202]
    r = valid_start(app, monkeypatch, "198.51.100.99")  # a different caller, but the shared budget is spent
    assert r.status_code == 429 and r.json()["detail"]["error"] == "RATE_LIMITED" and "daily limit" in r.json()["detail"]["message"]
    assert valid_start(app, monkeypatch, "198.51.100.99", admin=True).status_code == 202  # the presenter is never locked out


def test_requests_that_fail_validation_do_not_spend_the_daily_caps(tmp_path, monkeypatch):
    app = create_app(settings(tmp_path, run_daily_cap=1, order_daily_cap=1, run_rate_limit=(50, 600),
                              api_rate_limit=(50, 600), paypal_mode="mock", demo_admin_token=TOKEN))
    assert [start(app, f"198.51.100.{i}").status_code for i in range(3)] == [400] * 3  # bad store address
    with TestClient(app, base_url="https://testserver") as c:
        bad = {"sku": "NO-SUCH-SKU", "quantity": 1}
        assert [c.post("/api/paypal/orders", json=bad).status_code for _ in range(3)] == [404] * 3
        agent = {"sku": "FH-MUG-01", "quantity": 1, "vault_id": "MOCKVAULTABC123", "request_id": "req-0001-abcd"}
        assert c.post("/api/paypal/agent-orders", json={**agent, "max_amount": "0.01"}).status_code == 409  # over budget
        assert c.post("/api/paypal/orders", json={"sku": "FH-MUG-01", "quantity": 1}).status_code == 201  # cap still whole
        assert c.post("/api/paypal/orders", json={"sku": "FH-MUG-01", "quantity": 1}).status_code == 429  # now spent
    assert valid_start(app, monkeypatch, "198.51.100.50").status_code == 202  # the runs cap was never touched


def test_the_presenter_skips_the_per_address_limit(tmp_path):
    app = create_app(settings(tmp_path, run_rate_limit=(1, 600), demo_admin_token=TOKEN))
    assert [start(app, "203.0.113.7", admin=True).status_code for _ in range(3)] == [400, 400, 400]


def test_a_raw_token_cookie_is_not_the_presenter_unlock(tmp_path):
    app = create_app(settings(tmp_path, run_rate_limit=(1, 600), demo_admin_token=TOKEN))
    c = TestClient(app, base_url="https://testserver")
    c.cookies.set(ADMIN_COOKIE, TOKEN)
    assert c.get("/store/admin").status_code == 403
    assert [start(app, "203.0.113.7").status_code for _ in range(2)] == [400, 429]


# --- Mock PayPal scenario switch ---

def test_the_mock_scenario_switch_is_for_dev_or_the_presenter(tmp_path):
    app = create_app(settings(tmp_path, paypal_mode="mock", demo_admin_token=TOKEN))
    with TestClient(app, base_url="https://testserver") as c:
        assert c.get("/mock-paypal/scenario").status_code == 200
        assert c.put("/mock-paypal/scenario", json={"scenario": "no_button"}).status_code == 403
        assert c.get("/mock-paypal/scenario").json()["scenario"] == "ok"
        c.cookies.set(ADMIN_COOKIE, admin_cookie_value(TOKEN))
        assert c.put("/mock-paypal/scenario", json={"scenario": "no_button"}).status_code == 200
    dev = create_app(settings(tmp_path, paypal_mode="mock", dev_options=True))
    with TestClient(dev) as c:
        assert c.put("/mock-paypal/scenario", json={"scenario": "ok"}).status_code == 200


# --- Fetches are capped and pinned ---

class Counting(httpx.AsyncByteStream):
    def __init__(self, total: int):
        self.total, self.sent = total, 0

    async def __aiter__(self):
        while self.sent < self.total:
            self.sent += 65536
            yield b"a" * 65536


def serving(responses: dict[str, httpx.Response]):
    def handler(request: httpx.Request) -> httpx.Response:
        return responses.get(request.url.path) or httpx.Response(404)
    return httpx.MockTransport(handler)


@pytest.mark.anyio
async def test_a_huge_robots_txt_is_read_only_up_to_the_cap():
    body = Counting(50 * 1024 * 1024)
    polite = Politeness(allow_private=False, transport=serving({"/robots.txt": httpx.Response(200, stream=body)}))
    try:
        assert await polite.allowed("http://93.184.216.34/shop") is True
    finally:
        await polite.aclose()
    assert body.sent <= site.ROBOTS_MAX_BYTES + 65536
    assert len(polite.robots_texts["http://93.184.216.34"]) <= site.ROBOTS_MAX_BYTES


@pytest.mark.anyio
async def test_a_huge_store_page_is_not_buffered_by_the_preflight():
    page = Counting(50 * 1024 * 1024)
    polite = Politeness(allow_private=False, transport=serving(
        {"/": httpx.Response(200, headers={"content-type": "text/html"}, stream=page)}))
    target = await preflight("http://93.184.216.34/", "https://ghostshopper.example", polite)
    await polite.aclose()
    assert target.url == "http://93.184.216.34/" and page.sent <= 65536


@pytest.mark.anyio
async def test_errors_for_a_store_do_not_reveal_status_codes():
    polite = Politeness(allow_private=False, transport=serving(
        {"/": httpx.Response(500, headers={"content-type": "text/html"})}))
    with pytest.raises(SiteError) as err:
        await preflight("http://93.184.216.34/", "https://ghostshopper.example", polite)
    await polite.aclose()
    assert "500" not in str(err.value)


async def _noop():
    return None


def fake_dns(monkeypatch, *addresses: str):
    async def getaddrinfo(host, port, type=0):
        return [(0, 0, 0, "", (a, 0)) for a in addresses]
    monkeypatch.setattr(site.asyncio, "get_running_loop", lambda: SimpleNamespace(getaddrinfo=getaddrinfo))


@pytest.mark.parametrize("ip,allowed", [("100.64.0.1", False), ("100.100.100.200", False), ("10.0.0.5", False),
                                        ("169.254.169.254", False), ("8.8.8.8", True)])
def test_carrier_grade_nat_and_other_non_global_addresses_are_not_public(ip, allowed):
    assert site._is_public(ip) is allowed


@pytest.mark.anyio
async def test_a_name_with_any_private_address_is_refused(monkeypatch):
    fake_dns(monkeypatch, "93.184.216.34", "10.0.0.5")
    with pytest.raises(SiteError, match="public websites"):
        await resolve_checked("rebind.example", allow_private=False)
    assert await resolve_checked("rebind.example", allow_private=True) == "93.184.216.34"


@pytest.mark.anyio
async def test_the_connection_goes_to_the_validated_address_with_the_original_name(monkeypatch):
    fake_dns(monkeypatch, "93.184.216.34")
    seen = []

    async def inner(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200)

    transport = PinnedTransport(allow_private=False)
    transport._inner = SimpleNamespace(handle_async_request=inner, aclose=lambda: _noop())
    async with httpx.AsyncClient(transport=transport) as client:
        await client.get("https://shop.example/page")
    request = seen[0]
    assert request.url.host == "93.184.216.34" and request.headers["host"] == "shop.example"
    assert request.extensions["sni_hostname"] == "shop.example"


# --- Admin unlock ---

def test_the_unlock_cookie_holds_a_derived_value_not_the_token(tmp_path):
    app = create_app(settings(tmp_path, demo_admin_token=TOKEN))
    with TestClient(app, base_url="https://testserver") as c:
        r = c.post("/store/admin/unlock", data={"token": TOKEN}, follow_redirects=False)
        assert r.status_code == 303
        assert TOKEN not in r.headers["set-cookie"] and admin_cookie_value(TOKEN) in r.headers["set-cookie"]
        assert c.get("/store/admin").status_code == 200


def test_unlock_attempts_are_throttled_per_address(tmp_path):
    app = create_app(settings(tmp_path, demo_admin_token=TOKEN))
    with TestClient(app, base_url="https://testserver") as c:
        def guess(ip, token="wrong"):
            return c.post("/store/admin/unlock", data={"token": token}, headers={"X-Forwarded-For": ip}, follow_redirects=False)

        assert [guess("203.0.113.7").status_code for _ in range(10)] == [403] * 10
        assert guess("203.0.113.7", TOKEN).status_code == 429  # even the right token waits out the window
        assert guess("198.51.100.9", TOKEN).status_code == 303  # another address is not affected


def test_a_wrong_admin_token_header_shares_the_unlock_throttle(tmp_path):
    app = create_app(settings(tmp_path, demo_admin_token=TOKEN))
    with TestClient(app, base_url="https://testserver") as c:
        def guess(ip, token="wrong"):
            return c.get("/store/admin", headers={"X-Admin-Token": token, "X-Forwarded-For": ip})

        assert [guess("203.0.113.7").status_code for _ in range(10)] == [403] * 10
        assert guess("203.0.113.7").status_code == 429
        assert c.post("/store/admin/unlock", data={"token": "wrong"}, headers={"X-Forwarded-For": "203.0.113.7"}).status_code == 429
        assert guess("198.51.100.9", TOKEN).status_code == 200  # the right header still works from another address
        assert guess("198.51.100.9").status_code == 403


# --- Spending limit ---

@pytest.mark.parametrize("bad", ["abc", "NaN", "Infinity", "-5", ""])
def test_a_bad_max_amount_is_a_client_error(tmp_path, bad):
    dev = Settings(paypal_client_id="", paypal_client_secret="", database_path=tmp_path / "m.db",
                   app_base_url="http://localhost:8000", paypal_mode="mock", dev_options=True)
    body = {"sku": "FH-MUG-01", "quantity": 1, "vault_id": "MOCKVAULTABC123", "request_id": "req-0001-abcd", "max_amount": bad}
    with TestClient(create_app(dev, paypal=FakePayPalClient())) as c:
        r = c.post("/api/paypal/agent-orders", json=body)
    assert r.status_code == 422 and r.json()["detail"]["error"] == "BAD_MAX_AMOUNT"
