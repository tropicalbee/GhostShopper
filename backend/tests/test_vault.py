"""Vault agent payment: one-time setup stores a token, and the agent pays with it (mock PayPal, no popup)."""

from decimal import Decimal

import httpx
import pytest
from fastapi.testclient import TestClient

from backend.app import db, vault
from backend.app.agent.loop import goal_text
from backend.app.agent.paypal_flow import PaymentConfigError
from backend.app.agent.service import RunConfigError, RunRequest, build_payment
from backend.app.agent.vault_flow import make_vault_handler
from backend.app.config import Settings
from backend.app.main import create_app
from backend.app.paypal_mock import FakePayPalClient

from .test_agent_e2e import requires_browser
from .test_checkout_e2e import check, results, server  # noqa: F401  (server is a fixture)
from .test_checkout_e2e import RunConfig, apply_flaws, load_run, resolve_cassette, ReplayLLM, run_shopper

pytestmark = pytest.mark.anyio


def mock_settings(tmp_path) -> Settings:
    return Settings(paypal_client_id="", paypal_client_secret="", database_path=tmp_path / "v.db",
                    app_base_url="http://localhost:8000", paypal_mode="mock", dev_options=True)


async def save_token(settings: Settings) -> dict:
    client = FakePayPalClient()
    setup = await vault.setup_token(settings, client)
    assert vault.approve_link(setup).startswith("http://localhost:8000/api/paypal/vault/return")
    return await vault.finish_setup(settings, client, setup["id"])


async def test_setup_and_finish_store_a_token(tmp_path):
    settings = mock_settings(tmp_path)
    done = await save_token(settings)
    row = db.latest_vault_token(settings.database_path, "mock")
    assert row["payment_token_id"].startswith("MOCKVAULT") and row["customer_id"] == done["customer_id"]
    assert db.latest_vault_token(settings.database_path, "sandbox") is None  # tokens are per PayPal mode


async def test_finish_rejects_an_unknown_setup_token(tmp_path):
    with pytest.raises(vault.VaultError, match="PayPal refused"):
        await vault.finish_setup(mock_settings(tmp_path), FakePayPalClient(), "NOPE")


def test_sandbox_setup_without_credentials_is_an_explicit_error(tmp_path):
    settings = mock_settings(tmp_path)
    sandbox = Settings(**{**settings.__dict__, "paypal_mode": "sandbox"})
    with pytest.raises(vault.VaultError, match="PAYPAL_CLIENT_ID"):
        vault.make_client(sandbox)


async def test_missing_token_is_an_explicit_run_config_error(tmp_path):
    db.init_db(tmp_path / "v.db")
    req = RunRequest(llm="mock", checkout=True, paypal="mock", payment="vault")
    with pytest.raises(PaymentConfigError, match="vault setup"):
        make_vault_handler("mock", "http://x/store/", tmp_path / "v.db", server_mode="mock", server_configured=True)
    from backend.app.agent.service import ServerInfo
    with pytest.raises(RunConfigError, match="python -m backend.app.vault setup"):
        build_payment(req, "http://x/store/", ServerInfo("mock", True), db_path=tmp_path / "v.db")


async def test_vault_mode_mismatch_is_an_error(tmp_path):
    await save_token(mock_settings(tmp_path))
    with pytest.raises(PaymentConfigError, match="PAYPAL_MODE=mock"):
        make_vault_handler("sandbox", "http://x/store/", tmp_path / "v.db", server_mode="mock", server_configured=True)


def test_goal_names_the_vault_tool():
    text = goal_text("Mug", "http://x/store/", True, budget=Decimal("20.00"), pay_tool="pay_with_saved_paypal")
    assert "pay with pay_with_saved_paypal" in text and "do not call pay_with_saved_paypal" in text
    assert "pay_with_paypal" not in text


@pytest.fixture
def client(tmp_path):
    settings = mock_settings(tmp_path)
    fake = FakePayPalClient()
    with TestClient(create_app(settings, paypal=fake)) as c:
        c.fake = fake
        yield c


BODY = {"sku": "FH-MUG-01", "quantity": 1, "vault_id": "MOCKVAULTABC123", "request_id": "req-0001-abcd"}


def test_agent_order_captures_and_records(client):
    r = client.post("/api/paypal/agent-orders", json=BODY)
    assert r.status_code == 201, r.text
    got = r.json()
    assert (got["amount"], got["gross_amount"], got["paypal_fee"], got["net_amount"]) == ("24.00", "24.00", "1.33", "22.67")
    agent = {"X-GhostShopper-Key": client.app.state.internal_key}
    stored = client.get(f"/api/paypal/orders/{got['order_id']}", headers=agent).json()
    assert stored["capture_status"] == "COMPLETED" and stored["status"] == "COMPLETED"
    assert client.get(f"/api/paypal/orders/{got['order_id']}/verify", headers=agent).json()["ok"] is True
    assert "MOCKVAULTABC123" not in client.get(f"/api/paypal/orders/{got['order_id']}", headers=agent).text


def test_agent_order_captures_when_paypal_did_not(client):
    client.fake.vault_completes_immediately = False
    r = client.post("/api/paypal/agent-orders", json=BODY)
    assert r.status_code == 201, r.text
    assert client.get(f"/api/paypal/orders/{r.json()['order_id']}", headers={"X-GhostShopper-Key": client.app.state.internal_key}).json()["capture_status"] == "COMPLETED"


def test_agent_order_is_idempotent_for_the_same_request_id(client):
    first = client.post("/api/paypal/agent-orders", json=BODY).json()["order_id"]
    again = client.post("/api/paypal/agent-orders", json=BODY).json()["order_id"]
    assert first == again and len(client.fake.orders) == 1


def test_agent_order_over_budget_charges_nothing(client):
    r = client.post("/api/paypal/agent-orders", json={**BODY, "max_amount": "20.00"})
    assert r.status_code == 409 and r.json()["detail"]["error"] == "OVER_BUDGET"
    assert client.fake.orders == {}


def test_agent_order_bad_token_is_a_422(client):
    r = client.post("/api/paypal/agent-orders", json={**BODY, "vault_id": "WRONGTOKEN"})
    assert r.status_code == 422


@requires_browser
async def test_vault_payment_run_captures_and_verifies_without_a_popup(server):  # noqa: F811
    settings = mock_settings(server.db_path.parent)
    settings = Settings(**{**settings.__dict__, "database_path": server.db_path})
    await save_token(settings)
    store_url = f"{server.url}/store/"
    snapshot = await apply_flaws(store_url, "off")
    payment = make_vault_handler("mock", store_url, server.db_path, server_mode="mock", server_configured=True,
                                 internal_key=server.internal_key)
    cfg = RunConfig(store_url=store_url, db_path=server.db_path, flaws=snapshot, runs_dir=server.runs_dir,
                    checkout=True, paypal_mode="mock")
    run = load_run(server.db_path, await run_shopper(cfg, ReplayLLM(resolve_cassette("day3_checkout_vault")), payment))

    assert run["status"] == "completed", run["error"]
    assert run["outcome"] == "purchased" and run["score"]["total"] == 100
    assert all(v == 1 for v in results(run).values()), results(run)
    order = run["order"]
    assert order["capture_status"] == "COMPLETED" and order["run_id"] == run["id"]
    assert (order["gross_amount"], order["paypal_fee"], order["net_amount"]) == ("24.00", "1.33", "22.67")
    assert "no popup" in check(run, "popup_opened")["reason"].lower() or "No PayPal window" in check(run, "popup_opened")["reason"]
    assert any(s["tool"] == "pay_with_saved_paypal" and s["ok"] == 1 for s in run["steps"])

    # The token is a secret: not in any step, check, goal, or the stored run rows.
    token = db.latest_vault_token(server.db_path, "mock")
    secret = token["payment_token_id"]
    blob = repr(run["steps"]) + repr(run["checks"]) + str(run["goal"]) + str(run.get("summary"))
    assert secret not in blob and token["customer_id"] not in blob
    with db.connect(server.db_path) as conn:
        for table in ("steps", "checks", "runs"):
            dump = repr([tuple(r) for r in conn.execute(f"SELECT * FROM {table}")])
            assert secret not in dump, table
    assert not any(secret in p.read_text(errors="ignore") for p in server.runs_dir.rglob("*.json"))


@requires_browser
async def test_vault_payment_over_budget_is_refused_without_charging(server):  # noqa: F811
    settings = Settings(**{**mock_settings(server.db_path.parent).__dict__, "database_path": server.db_path})
    await save_token(settings)
    store_url = f"{server.url}/store/"
    snapshot = await apply_flaws(store_url, "off")
    payment = make_vault_handler("mock", store_url, server.db_path, server_mode="mock", server_configured=True,
                                 internal_key=server.internal_key)
    cfg = RunConfig(store_url=store_url, db_path=server.db_path, flaws=snapshot, runs_dir=server.runs_dir,
                    checkout=True, paypal_mode="mock", budget=Decimal("20.00"))
    run = load_run(server.db_path, await run_shopper(cfg, ReplayLLM(resolve_cassette("day3_checkout_vault")), payment))
    c = check(run, "paypal_button_found")
    assert (c["passed"], c["code"]) == (0, "over_budget") and run["order"] is None
    async with httpx.AsyncClient() as http:
        assert (await http.get(f"{server.url}/api/health")).status_code == 200


def test_deployed_sandbox_agent_order_needs_no_unlock(tmp_path):
    settings = Settings(paypal_client_id="id", paypal_client_secret="secret", database_path=tmp_path / "d.db",
                        app_base_url="https://shop.example.com", paypal_mode="sandbox", demo_admin_token="open-sesame")
    assert not settings.dev_options
    with TestClient(create_app(settings, paypal=FakePayPalClient())) as c:
        assert c.post("/api/paypal/agent-orders", json=BODY).status_code == 201


def test_mock_mode_agent_order_needs_no_unlock(tmp_path):
    settings = Settings(paypal_client_id="", paypal_client_secret="", database_path=tmp_path / "m.db",
                        app_base_url="https://shop.example.com", paypal_mode="mock")
    assert not settings.dev_options
    with TestClient(create_app(settings, paypal=FakePayPalClient())) as c:
        assert c.post("/api/paypal/agent-orders", json=BODY).status_code == 201


def test_agent_order_refuses_behind_an_account_wall(client):
    client.put("/store/admin/flaws.json", json={"flaws": {"no_guest_checkout": True}}).raise_for_status()
    r = client.post("/api/paypal/agent-orders", json=BODY)
    assert r.status_code == 403 and r.json()["detail"]["error"] == "ACCOUNT_REQUIRED"
    assert client.fake.orders == {}


@requires_browser
async def test_vault_run_behind_an_account_wall_creates_no_order(server):  # noqa: F811
    settings = Settings(**{**mock_settings(server.db_path.parent).__dict__, "database_path": server.db_path})
    await save_token(settings)
    store_url = f"{server.url}/store/"
    snapshot = await apply_flaws(store_url, "no_guest_checkout")
    payment = make_vault_handler("mock", store_url, server.db_path, server_mode="mock", server_configured=True,
                                 internal_key=server.internal_key)
    cfg = RunConfig(store_url=store_url, db_path=server.db_path, flaws=snapshot, runs_dir=server.runs_dir,
                    checkout=True, paypal_mode="mock")
    run = load_run(server.db_path, await run_shopper(cfg, ReplayLLM(resolve_cassette("day3_checkout_vault")), payment))
    c = check(run, "paypal_button_found")
    assert (c["passed"], c["code"]) == (0, "account_required") and run["order"] is None
    with db.connect(server.db_path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM orders").fetchone()[0] == 0


# --- a saved sandbox buyer for hosted servers whose database starts empty ----------------------------------

def sandbox_app(tmp_path, monkeypatch, **kw):
    for name, value in (("KERNEL_API_KEY", "k"), ("SANDBOX_BUYER_EMAIL", "b@example.test"), ("SANDBOX_BUYER_PASSWORD", "p")):
        monkeypatch.setenv(name, value)
    settings = Settings(paypal_client_id="", paypal_client_secret="", database_path=tmp_path / "v.db",
                        app_base_url="https://demo.example", paypal_mode="sandbox", dev_options=False, **kw)
    return create_app(settings, paypal=FakePayPalClient())


def test_the_environment_buyer_is_saved_at_startup_and_never_shown(tmp_path, monkeypatch):
    app = sandbox_app(tmp_path, monkeypatch, vault_token_id="TOKENSECRET123", vault_customer_id="CUST1")
    with TestClient(app, base_url="https://demo.example") as c:
        saved = db.latest_vault_token(tmp_path / "v.db", "sandbox")
        assert saved["payment_token_id"] == "TOKENSECRET123" and saved["customer_id"] == "CUST1"
        health = c.get("/api/health")
        assert health.json()["vault_ready"] is True and "TOKENSECRET123" not in health.text
    with TestClient(app, base_url="https://demo.example"):  # a restart does not add a second row
        pass
    with db.connect(tmp_path / "v.db") as conn:
        assert conn.execute("SELECT COUNT(*) FROM vault_tokens").fetchone()[0] == 1


def test_no_saved_buyer_means_vault_is_not_ready(tmp_path, monkeypatch):
    with TestClient(sandbox_app(tmp_path, monkeypatch), base_url="https://demo.example") as c:
        assert c.get("/api/health").json()["vault_ready"] is False


@pytest.mark.parametrize("token, expected, browser", [("TOKENSECRET123", "vault", None), ("", "popup", "kernel")])
def test_a_real_sandbox_run_defaults_to_the_vault_only_when_a_buyer_is_saved(tmp_path, monkeypatch, token, expected, browser):
    from backend.app import runs

    seen = []

    async def fake_execute(req, url, db_path, on_start=None, **kw):
        seen.append(req)
        on_start(1)

    monkeypatch.setattr(runs, "live_llm_configured", lambda: True)
    monkeypatch.setattr(runs, "execute", fake_execute)
    monkeypatch.setattr(runs, "prepare", lambda *a, **k: (None, None))
    with TestClient(sandbox_app(tmp_path, monkeypatch, vault_token_id=token), base_url="https://demo.example") as c:
        assert c.post("/api/runs", json={"real_payment": True}).status_code == 202
    assert seen[0].payment == expected
    assert seen[0].browser == browser  # only a popup needs Kernel's live view; a vault run uses BROWSER_PROVIDER
