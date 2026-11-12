"""The Fernhill WebMCP adapter's server: catalog reads, and checkout through the same code as the PayPal button."""

import pytest
from fastapi.testclient import TestClient

from backend.app.config import Settings
from backend.app.main import create_app
from backend.app.paypal_mock import FakePayPalClient
from backend.app.webmcp.tools import SHOPPING_TOOLS, function_names

SKU = "FH-MUG-01"


@pytest.fixture
def client(tmp_path):
    settings = Settings(paypal_client_id="", paypal_client_secret="", database_path=tmp_path / "wm.db",
                        app_base_url="http://localhost:8000", paypal_mode="mock", dev_options=True)
    fake = FakePayPalClient()
    with TestClient(create_app(settings, paypal=fake)) as c:
        c.fake = fake
        yield c


def call(client, tool, **tool_input) -> dict:
    r = client.post("/store/webmcp/rpc", json={"jsonrpc": "2.0", "id": 7, "tool": tool, "input": tool_input})
    assert r.status_code == 200, r.text
    assert r.json()["id"] == 7
    return r.json()


def result(client, tool, **tool_input) -> dict:
    body = call(client, tool, **tool_input)
    assert "error" not in body, body
    return body["result"]


def test_function_names_replace_the_dot_and_stay_unique():
    names = function_names(list(SHOPPING_TOOLS))
    assert names["shopping.searchProducts"] == "shopping__searchProducts"
    assert len(set(names.values())) == 4
    clash = function_names(["a.b", "a__b"])
    assert clash["a.b"] != clash["a__b"]


def test_search_returns_products_with_a_price_and_availability(client):
    found = result(client, "shopping.searchProducts", query="speckled mug")["products"]
    assert found and found[0]["product_id"] == SKU
    assert found[0]["price"] == {"value": "24.00", "currency_code": "USD"}
    assert found[0]["availability"] in ("in_stock", "out_of_stock") and found[0]["url"].endswith("/store/products/" + found[0]["url"].rsplit("/", 1)[1])
    assert len(result(client, "shopping.searchProducts", query="a", max_results=2)["products"]) <= 2


def test_get_product_by_sku_and_unknown_product(client):
    assert result(client, "shopping.getProduct", product_id=SKU)["title"] == "Speckled Stoneware Mug"
    assert call(client, "shopping.getProduct", product_id="NOPE")["error"]["code"] == -32602
    assert call(client, "shopping.getProduct")["error"]["code"] == -32602


def test_ui_flaws_do_not_change_tool_results(client):
    before = result(client, "shopping.getProduct", product_id=SKU)
    client.put("/store/admin/flaws.json", json={"flaws": {
        "price_as_image": True, "no_structured_data": True, "ambiguous_buttons": True, "extra_checkout_step": True,
        "cookie_banner": True}}).raise_for_status()
    assert result(client, "shopping.getProduct", product_id=SKU) == before


def test_unknown_tool_and_bad_input_are_json_rpc_errors(client):
    assert call(client, "shopping.nope")["error"]["code"] == -32601
    assert call(client, "shopping.searchProducts")["error"]["code"] == -32602
    assert call(client, "shopping.searchProducts", query="mug", surprise=1)["error"]["code"] == -32602
    assert call(client, "shopping.initiateCheckout", product_id=SKU, quantity=6, requires_user_approval=True)["error"]["code"] == -32602


def test_checkout_needs_the_approval_flag(client):
    for flag in ({}, {"requires_user_approval": False}):
        err = call(client, "shopping.initiateCheckout", product_id=SKU, **flag)["error"]
        assert err["code"] == -32602 and "requires_user_approval" in err["message"]
    assert client.fake.orders == {}


def test_initiate_creates_the_store_order_and_a_payer_action_link(client):
    out = result(client, "shopping.initiateCheckout", product_id=SKU, quantity=2, requires_user_approval=True)
    assert out["cart_id"] == "1042" and out["quantity"] == 2 and out["product_id"] == SKU
    assert out["amount"] == {"value": "48.00", "currency_code": "USD"} and out["status"] == "PAYER_ACTION_REQUIRED"
    assert out["approval_url"].endswith(f"/mock-paypal/checkout?token={out['order_id']}")
    order = client.fake.orders[out["order_id"]]
    assert order["purchase_unit"]["custom_id"] == "1042"
    context = order["experience_context"]
    assert context["return_url"].endswith("/store/webmcp/return") and context["cancel_url"].endswith("?cancelled=1")
    assert "Awaiting payment" in client.get("/store/orders/1042").text


def test_complete_captures_through_the_store_capture_path(client):
    out = result(client, "shopping.initiateCheckout", product_id=SKU, requires_user_approval=True)
    done = result(client, "shopping.completeCheckout", cart_id=out["cart_id"], token=out["order_id"])
    assert done["status"] == "COMPLETED" and done["capture_id"].startswith("MOCKCAP")
    assert done["amount"] == {"value": "24.00", "currency_code": "USD"} and done["store_order_number"] == 1042
    assert done["order_url"].endswith("/store/orders/1042")
    assert "Paid" in client.get("/store/orders/1042").text


def test_purchase_flaws_apply_to_the_webmcp_path(client):
    client.put("/store/admin/flaws.json", json={"flaws": {"never_marks_paid": True}}).raise_for_status()
    out = result(client, "shopping.initiateCheckout", product_id=SKU, requires_user_approval=True)
    result(client, "shopping.completeCheckout", token=out["order_id"])
    assert "Awaiting payment" in client.get("/store/orders/1042").text


def test_price_mismatch_flaw_charges_more_than_the_tools_advertise(client):
    client.put("/store/admin/flaws.json", json={"flaws": {"price_mismatch": True}}).raise_for_status()
    advertised = result(client, "shopping.getProduct", product_id=SKU)["price"]["value"]
    out = result(client, "shopping.initiateCheckout", product_id=SKU, requires_user_approval=True)
    assert advertised == "24.00" and out["amount"]["value"] == "27.00"


def test_complete_rejects_a_missing_unknown_or_foreign_token(client):
    assert call(client, "shopping.completeCheckout")["error"]["code"] == -32602
    assert call(client, "shopping.completeCheckout", token="NOSUCHORDER1")["error"]["code"] == -32602
    out = result(client, "shopping.initiateCheckout", product_id=SKU, requires_user_approval=True)
    assert call(client, "shopping.completeCheckout", cart_id="9999", token=out["order_id"])["error"]["code"] == -32602


def test_a_declined_capture_is_a_tool_error_and_the_store_order_fails(client):
    out = result(client, "shopping.initiateCheckout", product_id=SKU, requires_user_approval=True)
    client.fake.scenario = "capture_declined"
    err = call(client, "shopping.completeCheckout", token=out["order_id"])["error"]
    assert err["code"] == -32000 and err["data"]["issue"] == "INSTRUMENT_DECLINED"
    assert "Payment failed" in client.get("/store/orders/1042").text


def test_the_return_page_says_approved_and_closes_the_window(client):
    page = client.get("/store/webmcp/return?token=X").text
    assert "Payment approved, you can close this window" in page and "window.close()" in page
    assert "cancelled" in client.get("/store/webmcp/return?cancelled=1").text


def test_every_store_page_loads_the_adapter(client):
    assert 'webmcp.js' in client.get("/store/").text
    assert "navigator" in client.get("/store/static/webmcp.js").text


def test_mock_approval_page_returns_to_the_given_urls(client):
    out = result(client, "shopping.initiateCheckout", product_id=SKU, requires_user_approval=True)
    page = client.get(f"/mock-paypal/checkout?token={out['order_id']}").text
    assert "/store/webmcp/return" in page and "payment-submit-btn" in page
