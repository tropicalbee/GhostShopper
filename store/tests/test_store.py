import json
import re

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from store.app import create_store_app
from store.flaws import FLAW_KEYS


@pytest.fixture
def client(tmp_path):
    app = FastAPI()
    app.mount(
        "/store",
        create_store_app(
            db_path=tmp_path / "store.db",
            paypal_client_id="test-client-id",
            paypal_sdk_url="https://www.sandbox.paypal.com/web-sdk/v6/core",
        ),
    )
    with TestClient(app) as c:
        yield c


def set_flaws(client, **flaws):
    r = client.put("/store/admin/flaws.json", json={"flaws": flaws})
    assert r.status_code == 200
    return r.json()


def all_off(client):
    return set_flaws(client, **{k: False for k in FLAW_KEYS})


PRODUCT = "/store/products/speckled-stoneware-mug"


def test_classic_flaws_default_on_new_ones_off(client):
    from store.flaws import CLASSIC_FLAWS

    assert client.get("/store/admin/flaws.json").json() == {k: k in CLASSIC_FLAWS for k in FLAW_KEYS}


def test_unknown_flaw_rejected(client):
    assert client.put("/store/admin/flaws.json", json={"flaws": {"nope": True}}).status_code == 422


def test_admin_form_toggles(client):
    r = client.post("/store/admin", data={"price_as_image": "on"}, follow_redirects=False)
    assert r.status_code == 303
    assert client.get("/store/admin/flaws.json").json() == {k: k == "price_as_image" for k in FLAW_KEYS}


def test_price_as_image(client):
    html = client.get(PRODUCT).text
    assert "$24.00" not in html
    src = re.search(r'class="price-img" src="([^"]+)"', html).group(1)
    svg = client.get(src)
    assert svg.headers["content-type"].startswith("image/svg+xml")
    assert "<text" not in svg.text and "24" not in src

    set_flaws(client, price_as_image=False)
    html = client.get(PRODUCT).text
    assert '<span class="price">$24.00</span>' in html
    assert "price-img" not in html


def test_structured_data_toggle(client):
    html = client.get(PRODUCT).text
    assert "application/ld+json" not in html
    assert 'name="description"' not in html
    assert "SKU:" not in html and "In stock" not in html

    set_flaws(client, no_structured_data=False)
    html = client.get(PRODUCT).text
    data = json.loads(re.search(r'<script type="application/ld\+json">(.*?)</script>', html, re.S).group(1))
    assert data["@type"] == "Product"
    assert data["sku"] == "FH-MUG-01"
    assert data["offers"]["price"] == "24.00"
    assert data["offers"]["priceCurrency"] == "USD"
    assert data["offers"]["availability"] == "https://schema.org/InStock"
    assert "<h1>Speckled Stoneware Mug</h1>" in html


def test_ambiguous_buttons_toggle(client):
    html = client.get(PRODUCT).text
    labels = re.findall(r'<div class="act [^"]+"[^>]*>([^<]+)</div>', html)
    assert labels == ["Continue", "Proceed", "Go", "&rarr;"]
    assert "<button" not in html

    set_flaws(client, ambiguous_buttons=False)
    html = client.get(PRODUCT).text
    assert '<button type="submit" class="buy">Buy now</button>' in html
    assert 'class="act ' not in html


def test_extra_checkout_step(client):
    r = client.get("/store/checkout?sku=FH-MUG-01", follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == "/store/checkout/details?sku=FH-MUG-01"

    r = client.post("/store/checkout/details", data={"sku": "FH-MUG-01", "email": "a@b.co"})
    assert "must agree" in r.text and "how you heard" in r.text

    r = client.post(
        "/store/checkout/details",
        data={"sku": "FH-MUG-01", "email": "a@b.co", "referral": "A friend", "agree": "yes"},
        follow_redirects=False,
    )
    assert r.status_code == 303
    assert "paypal-button" in client.get(r.headers["location"]).text


def test_direct_checkout_when_step_off(client):
    all_off(client)
    html = client.get(PRODUCT).text
    assert 'action="/store/checkout"' in html
    r = client.get("/store/checkout?sku=FH-MUG-01")
    assert r.status_code == 200
    assert '<paypal-button id="paypal-button" type="pay" hidden>' in r.text
    assert 'src="https://www.sandbox.paypal.com/web-sdk/v6/core"' in r.text
    assert 'data-client-id="test-client-id"' in r.text


def test_checkout_without_client_id_says_so(tmp_path):
    app = FastAPI()
    app.mount("/store", create_store_app(db_path=tmp_path / "s.db", paypal_client_id="", paypal_sdk_url="x"))
    with TestClient(app) as c:
        set_flaws(c, extra_checkout_step=False)
        html = c.get("/store/checkout?sku=FH-MUG-01").text
        assert "PayPal is not configured" in html
        assert "web-sdk" not in html and "paypal-button" not in html


def test_out_of_stock_has_no_buy(client):
    all_off(client)
    html = client.get("/store/products/espresso-cup-set").text
    assert "Buy now" not in html and "Sold out" in html
    assert "OutOfStock" in html


def test_index_lists_products(client):
    html = client.get("/store/").text
    for name in ("Speckled Stoneware Mug", "Pour-Over Coffee Dripper", "Ash Glaze Serving Bowl", "Espresso Cup Set (4)"):
        assert name in html


# --- Saboteur flaws (default off) ---

def only(client, flaw):
    return set_flaws(client, **{k: k == flaw for k in FLAW_KEYS})


def test_price_mismatch_raises_the_checkout_price(client):
    only(client, "price_mismatch")
    assert '<span class="price">$24.00</span>' in client.get(PRODUCT).text
    html = client.get("/store/checkout?sku=FH-MUG-01").text
    assert html.count('<span class="price">$27.00</span>') == 2  # item row and total


def test_oos_buyable_says_sold_out_but_keeps_the_button(client):
    only(client, "oos_buyable")
    html = client.get(PRODUCT).text
    assert "Sold out" in html and "Buy now" in html and "OutOfStock" in html
    assert "Buy now" in client.get("/store/products/espresso-cup-set").text  # even the genuinely sold-out set
    assert "paypal-button" in client.get("/store/checkout?sku=FH-ESP-04").text


def test_image_alt_missing_uses_a_file_name(client):
    only(client, "image_alt_missing")
    assert 'alt="IMG_0412.JPG"' in client.get(PRODUCT).text
    assert 'alt="IMG_0412.JPG"' in client.get("/store/").text


def test_cookie_banner_covers_buy_until_accepted(client):
    only(client, "cookie_banner")
    assert 'id="cookie-banner"' in client.get(PRODUCT).text
    client.cookies.set("fh_cookies", "1")
    assert 'id="cookie-banner"' not in client.get(PRODUCT).text


def test_currency_missing_drops_symbol_and_jsonld_currency(client):
    only(client, "currency_missing")
    html = client.get(PRODUCT).text
    assert '<span class="price">24.00</span>' in html
    assert "priceCurrency" not in html


def test_misleading_sale_shows_a_fake_was_price(client):
    only(client, "misleading_sale")
    html = client.get(PRODUCT).text
    assert "<s>$30.00</s>" in html and "50% off!" in html  # 24 vs 30 is 20% off, not 50%


# --- PayPal setup flaws (on = the feature is missing) ---

CHECKOUT = "/store/checkout?sku=FH-MUG-01"


def test_paypal_flaws_on_store_has_no_extra_paypal_features(client):
    from store.flaws import PAYPAL_FLAWS

    assert all(client.get("/store/admin/flaws.json").json()[k] for k in PAYPAL_FLAWS)
    set_flaws(client, **{k: False for k in FLAW_KEYS if k not in PAYPAL_FLAWS}, **{k: True for k in PAYPAL_FLAWS})
    product, checkout = client.get(PRODUCT).text, client.get(CHECKOUT).text
    assert "paypal-button" not in product and "paypal-message" not in product
    assert "venmo-button" not in checkout and "paypal-pay-later-button" not in checkout
    assert "paypal-basic-card-button" not in checkout and "debit or credit card" not in checkout
    assert "<paypal-button" in checkout and "paypal-guest-payments" not in checkout


def test_paypal_flaws_off_store_has_every_paypal_feature(client):
    all_off(client)
    product, checkout = client.get(PRODUCT).text, client.get(CHECKOUT).text
    assert "<paypal-button" in product and "<paypal-message" in product
    assert "checkout.js" in product and "web-sdk/v6/core" in product
    for tag in ("<venmo-button", "<paypal-pay-later-button", "<paypal-basic-card-button", "debit or credit card"):
        assert tag in checkout
    assert "paypal-guest-payments" in checkout


@pytest.mark.parametrize("flaw,present_when_off", [
    ("no_paypal_express", ("product", "<paypal-button")),
    ("no_pay_later", ("product", "<paypal-message")),
    ("no_pay_later", ("checkout", "<paypal-pay-later-button")),
    ("no_venmo", ("checkout", "<venmo-button")),
    ("no_card_checkout", ("checkout", "<paypal-basic-card-button")),
])
def test_each_paypal_flaw_controls_only_its_feature(client, flaw, present_when_off):
    page, needle = present_when_off
    url = PRODUCT if page == "product" else CHECKOUT
    only(client, flaw)
    assert needle not in client.get(url).text
    all_off(client)
    assert needle in client.get(url).text


def test_admin_lists_the_paypal_flaws(client):
    from store.flaws import PAYPAL_FLAWS

    html = client.get("/store/admin").text
    for key in PAYPAL_FLAWS:
        assert f'name="{key}"' in html


def test_no_guest_checkout_shows_an_account_wall_and_hides_paypal(client):
    from store.flaws import CLASSIC_FLAWS

    assert "no_guest_checkout" not in CLASSIC_FLAWS
    assert client.get("/store/admin/flaws.json").json()["no_guest_checkout"] is False
    only(client, "no_guest_checkout")
    html = client.get("/store/checkout?sku=FH-MUG-01").text
    assert 'type="password"' in html and "Create account" in html
    assert "paypal-button" not in html and "checkout.js" not in html
    posted = client.post("/store/checkout/account", data={"sku": "FH-MUG-01", "email": "a@b.test", "password": "longenough"})
    assert posted.status_code == 200 and "confirmation link" in posted.text and "paypal-button" not in posted.text
    all_off(client)
    assert 'type="password"' not in client.get("/store/checkout?sku=FH-MUG-01").text
