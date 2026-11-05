from backend.app.agent.checks import (
    evaluate_path_to_checkout,
    evaluate_product_page,
    is_checkout_page,
    is_product_page,
)

GOOD_JSONLD = {
    "@context": "https://schema.org",
    "@type": "Product",
    "name": "Speckled Stoneware Mug",
    "sku": "FH-MUG-01",
    "offers": {"@type": "Offer", "price": "24.00", "priceCurrency": "USD", "availability": "https://schema.org/InStock"},
}


def facts(**over):
    base = {
        "url": "http://shop/products/mug",
        "title": "Speckled Stoneware Mug | Fernhill Ceramics",
        "main_text": "Speckled Stoneware Mug\n$24.00\nSKU: FH-MUG-01 · In stock\nWheel-thrown mug.",
        "jsonld": [GOOD_JSONLD],
        "images_without_alt": [],
        "controls": [{"id": "e1", "tag": "button", "text": "Buy now", "semantic": True, "selector": "button.buy"}],
        "forms": [],
        "has_payment_button": False,
    }
    return base | over


def by_key(outcomes):
    return {o.key: o for o in outcomes}


def test_fixed_product_page_passes_everything():
    out = by_key(evaluate_product_page(facts()))
    assert all(o.passed for o in out.values()), {k: o.reason for k, o in out.items() if not o.passed}
    assert set(out) == {"price_in_text", "structured_data", "stock_readable", "clear_buy_button", "currency_stated",
                        "stock_consistent", "image_alt_text", "sale_claim_consistent", "buy_button_unobstructed"}


def test_price_only_in_image_fails_with_image_evidence():
    out = by_key(evaluate_product_page(facts(
        main_text="Speckled Stoneware Mug\nWheel-thrown mug.",
        images_without_alt=[{"selector": "div.product-price > img.price-img", "src": "/media/p/ab12.svg"}],
    )))
    assert out["price_in_text"].passed is False
    assert out["price_in_text"].evidence["selector"] == "div.product-price > img.price-img"
    assert "1 image(s) without alt" in out["price_in_text"].reason


def test_missing_jsonld_fails_and_partial_jsonld_lists_missing_fields():
    assert by_key(evaluate_product_page(facts(jsonld=[])))["structured_data"].passed is False
    partial = {"@type": "Product", "name": "Mug", "offers": {"price": "24.00"}}
    o = by_key(evaluate_product_page(facts(jsonld=[partial])))["structured_data"]
    assert o.passed is False
    assert o.evidence["missing"] == ["offers.priceCurrency", "offers.availability"]


def test_jsonld_in_graph_is_found():
    o = by_key(evaluate_product_page(facts(jsonld=[{"@graph": [{"@type": "WebPage"}, GOOD_JSONLD]}])))
    assert o["structured_data"].passed is True


def test_stock_from_text_only_or_jsonld_only():
    no_ld_text_stock = facts(jsonld=[], main_text="Mug $24.00 In stock")
    assert by_key(evaluate_product_page(no_ld_text_stock))["stock_readable"].passed is True
    ld_only = facts(main_text="Mug $24.00")
    assert by_key(evaluate_product_page(ld_only))["stock_readable"].passed is True
    neither = facts(jsonld=[], main_text="Mug $24.00")
    assert by_key(evaluate_product_page(neither))["stock_readable"].passed is False


def test_div_buttons_with_vague_labels_fail_clear_buy_button():
    controls = [
        {"id": "e5", "tag": "div", "text": "Continue", "semantic": False, "selector": "div.act.act-a"},
        {"id": "e6", "tag": "div", "text": "Go", "semantic": False, "selector": "div.act.act-c"},
        {"id": "e1", "tag": "a", "text": "Shop", "semantic": True, "selector": "nav > a"},
    ]
    o = by_key(evaluate_product_page(facts(controls=controls)))["clear_buy_button"]
    assert o.passed is False
    assert o.evidence["selector"] == "div.act.act-a"
    assert "'Continue', 'Go'" in o.reason


def test_div_labelled_buy_is_still_not_a_semantic_button():
    controls = [{"id": "e1", "tag": "div", "text": "Buy now", "semantic": False, "selector": "div.x"}]
    assert by_key(evaluate_product_page(facts(controls=controls)))["clear_buy_button"].passed is False


def test_page_classification():
    assert is_product_page(facts(), "speckled stoneware mug")
    assert not is_product_page(facts(title="Fernhill Ceramics"), "Speckled Stoneware Mug")
    assert is_checkout_page(facts(title="Checkout | Fernhill Ceramics"))
    assert is_checkout_page(facts(title="Pay", has_payment_button=True))
    assert not is_checkout_page(facts(title="Your details | Fernhill Ceramics"))


def test_path_to_checkout():
    assert evaluate_path_to_checkout("http://shop/checkout", []).passed is True
    o = evaluate_path_to_checkout("http://shop/checkout", [
        {"url": "http://shop/checkout/details", "selector": "form.details-form", "fields": ["Email", "Agree"]},
    ])
    assert o.passed is False
    assert o.evidence["url"] == "http://shop/checkout/details"
    assert "fields: Email, Agree" in o.reason


# --- Saboteur detectors ---

def price(text, value, currency=True):
    return {"text": text, "value": value, "currency": currency, "selector": "span.price"}


def test_currency_missing_in_text_or_jsonld():
    ld = {**GOOD_JSONLD, "offers": {k: v for k, v in GOOD_JSONLD["offers"].items() if k != "priceCurrency"}}
    o = by_key(evaluate_product_page(facts(prices=[price("24.00", "24.00", False)], jsonld=[ld])))["currency_stated"]
    assert (o.passed, o.code) == (False, "currency_missing")
    assert "24.00" in o.reason and "priceCurrency" in o.reason
    assert by_key(evaluate_product_page(facts(prices=[price("$24.00", "24.00")])))["currency_stated"].passed


def test_currency_untested_when_no_price_is_readable():
    assert "currency_stated" not in by_key(evaluate_product_page(facts(prices=[], jsonld=[])))


def test_sold_out_but_buyable_is_inconsistent():
    f = facts(main_text="Mug $24.00 Sold out", controls=[
        {"id": "e5", "tag": "button", "text": "Buy now", "semantic": True, "selector": "button.buy", "in_main": True}])
    o = by_key(evaluate_product_page(f))["stock_consistent"]
    assert (o.passed, o.code) == (False, "oos_still_buyable")
    honest = facts(main_text="Mug $24.00 Sold out", controls=[])
    assert by_key(evaluate_product_page(honest))["stock_consistent"].passed


def test_photo_alt_text_must_describe_the_product():
    bad = facts(images=[{"selector": "img.product-img", "alt": "IMG_0412.JPG", "src": "/mug.svg"}])
    o = by_key(evaluate_product_page(bad))["image_alt_text"]
    assert (o.passed, o.code) == (False, "image_alt_missing")
    for alt in ("", "photo", "DSC_0001"):
        assert not by_key(evaluate_product_page(facts(images=[{"selector": "i", "alt": alt}])))["image_alt_text"].passed
    good = facts(images=[{"selector": "img", "alt": "Speckled Stoneware Mug"}])
    assert by_key(evaluate_product_page(good))["image_alt_text"].passed


def test_sale_claim_must_match_the_real_discount():
    lie = facts(prices=[price("$24.00", "24.00")], struck_prices=[price("$30.00", "30.00")], sale_percent=50)
    o = by_key(evaluate_product_page(lie))["sale_claim_consistent"]
    assert (o.passed, o.code) == (False, "sale_claim_misleading")
    assert o.evidence["actual_percent_off"] == 20.0
    honest = facts(prices=[price("$24.00", "24.00")], struck_prices=[price("$30.00", "30.00")], sale_percent=20)
    assert by_key(evaluate_product_page(honest))["sale_claim_consistent"].passed
    assert by_key(evaluate_product_page(facts()))["sale_claim_consistent"].passed  # no claim at all


def test_sale_claim_uses_jsonld_price_when_text_price_is_unreadable():
    f = facts(prices=[], struck_prices=[price("$30.00", "30.00")], sale_percent=50)
    assert by_key(evaluate_product_page(f))["sale_claim_consistent"].passed is False


def test_covered_buy_button_is_detected():
    f = facts(controls=[{"id": "e5", "tag": "button", "text": "Buy now", "semantic": True, "selector": "button.buy",
                         "in_main": True, "covered": True, "covered_by": "div#cookie-banner"}])
    o = by_key(evaluate_product_page(f))["buy_button_unobstructed"]
    assert (o.passed, o.code) == (False, "buy_button_covered")
    assert o.evidence["covered_by"] == "div#cookie-banner"


def test_checkout_price_must_match_the_product_page():
    from decimal import Decimal

    from backend.app.agent.checks import evaluate_checkout_prices

    co = {"url": "http://shop/checkout", "prices": [price("$27.00", "27.00")]}
    o = evaluate_checkout_prices(co, Decimal("24.00"))[0]
    assert (o.passed, o.code) == (False, "price_changed_at_checkout")
    assert evaluate_checkout_prices(co, Decimal("27.00"))[0].passed
    assert evaluate_checkout_prices(co, None) == []  # product price was not text: untested
