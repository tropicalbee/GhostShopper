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
    assert {k: o.passed for k, o in out.items()} == {
        "price_in_text": True,
        "structured_data": True,
        "stock_readable": True,
        "clear_buy_button": True,
    }


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
