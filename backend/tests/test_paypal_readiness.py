"""PayPal readiness: the detector on small HTML fixtures, the scoring weights, and a mock demo-store run."""

from pathlib import Path

import pytest

from backend.app.agent.browser import FACTS_JS
from backend.app.agent.paypal_readiness import (DOCS, WEIGHTS, PayPalCollector, build_readiness, page_kind, parse_sdk)

from .test_agent_e2e import requires_browser, run_cassette, server  # noqa: F401  (server is a fixture)

FIXTURES = Path(__file__).parent / "fixtures" / "paypal"


async def scan(name: str) -> dict:
    """Load a fixture in Chromium (PayPal hosts answered with an empty script) and return its raw signals."""
    from playwright.async_api import async_playwright

    async with async_playwright() as pw:
        browser = await pw.chromium.launch()
        page = await browser.new_page()

        async def empty(route):
            await route.fulfill(status=200, content_type="application/javascript", body="")

        await page.route("**/*paypal.com/**", empty)
        await page.set_content((FIXTURES / name).read_text(encoding="utf-8"))
        facts = await page.evaluate(FACTS_JS)
        await browser.close()
    return facts["paypal_signals"]


def readiness_of(raw: dict, kind: str = "product") -> dict:
    c = PayPalCollector()
    c.add("http://x/p", kind, raw)
    return c.result()


def item(result: dict, key: str) -> dict:
    return next(i for i in result["checklist"] if i["key"] == key)


# --- Pure logic (no browser) ---

def test_weights_sum_to_100():
    assert sum(WEIGHTS.values()) == 100


def test_sdk_parsing_reads_v5_query_and_recognises_v6():
    v5 = parse_sdk(["https://www.paypal.com/sdk/js?client-id=abc&components=buttons,messages&enable-funding=venmo&currency=USD&intent=capture"])
    assert v5["version"] == "v5" and v5["components"] == ["buttons", "messages"]
    assert v5["enable_funding"] == ["venmo"] and v5["currency"] == "USD" and v5["intent"] == "capture"
    assert "abc" not in v5["src"]
    assert parse_sdk(["https://www.sandbox.paypal.com/web-sdk/v6/core"])["version"] == "v6"
    assert parse_sdk(["https://example.com/app.js"]) is None


def test_page_kind():
    assert page_kind("http://s/products/mug", True, False) == "product"
    assert page_kind("http://s/cart", False, True) == "cart"
    assert page_kind("http://s/store/checkout?sku=1", False, True) == "checkout"
    assert page_kind("http://s/about", False, False) == "other"


def test_no_pages_gives_no_result_and_no_paypal_scores_zero():
    assert build_readiness([]) is None
    r = readiness_of({"scripts": [], "elements": [], "buttons": []})
    assert r["score"] == 0 and r["paypal_found"] is False
    assert r["recommendations"][0]["key"] == "add_paypal"


def test_steps_from_product_to_first_visible_button():
    c = PayPalCollector()
    c.add("http://s/p", "product", {"buttons": []})
    c.add("http://s/cart", "cart", {"buttons": []})
    c.add("http://s/checkout", "checkout", {"scripts": ["https://www.sandbox.paypal.com/web-sdk/v6/core"],
                                            "buttons": [{"selector": "paypal-button", "visible": True}]})
    r = c.result()
    assert r["steps_to_paypal"] == 2
    assert item(r, "express")["points"] == 6
    assert r["placement"] == {"product": False, "cart": False, "checkout": True}
    c.add("http://s/p", "product", {"buttons": [{"selector": "paypal-button", "visible": True}]})
    assert c.result()["steps_to_paypal"] == 0 and item(c.result(), "express")["points"] == 18


def test_venmo_from_funding_setting_is_not_confirmed():
    raw = {"scripts": ["https://www.paypal.com/sdk/js?client-id=x&enable-funding=venmo"],
           "buttons": [{"selector": "div.paypal-buttons", "visible": True}]}
    r = readiness_of(raw)
    assert item(r, "venmo")["status"] == "not_confirmed" and item(r, "venmo")["points"] == 5
    rec = next(x for x in r["recommendations"] if x["key"] == "venmo")
    assert rec["title"].startswith("Confirm Venmo")
    assert item(readiness_of({**raw, "elements": [{"tag": "venmo-button", "visible": True}]}), "venmo")["status"] == "detected"


def test_recommendations_carry_docs_urls_and_sort_by_gain():
    r = readiness_of({"scripts": ["https://www.paypal.com/sdk/js?client-id=x"], "buttons": [{"selector": "b", "visible": True}]})
    assert all(x["docs_url"].startswith("https://developer.paypal.com/") for x in r["recommendations"])
    gains = [x["points"] for x in r["recommendations"]]
    assert gains == sorted(gains, reverse=True)
    assert any(x["title"] == "Upgrade JS SDK v5 to v6" and x["docs_url"] == DOCS["upgrade"] for x in r["recommendations"])


# --- Detector on real HTML in Chromium ---

@requires_browser
@pytest.mark.anyio
async def test_v6_page():
    r = readiness_of(await scan("v6.html"))
    assert item(r, "sdk")["status"] == "detected" and r["sdk"]["version"] == "v6"
    assert item(r, "button")["status"] == "detected"
    assert item(r, "messaging")["status"] == "detected"
    assert item(r, "express")["points"] == 18
    assert item(r, "venmo")["status"] == "missing"
    assert r["score"] == 20 + 20 + 18 + 12


@requires_browser
@pytest.mark.anyio
async def test_v5_page_with_pay_later_and_venmo():
    r = readiness_of(await scan("v5.html"))
    assert r["sdk"]["version"] == "v5" and r["sdk"]["currency"] == "USD" and r["sdk"]["intent"] == "capture"
    assert item(r, "sdk")["status"] == "partial"
    assert item(r, "messaging")["status"] == "detected"
    assert item(r, "paylater")["status"] == "detected"
    assert item(r, "venmo")["status"] == "not_confirmed"
    assert item(r, "card")["status"] == "detected"
    assert any(x["title"] == "Upgrade JS SDK v5 to v6" for x in r["recommendations"])


@requires_browser
@pytest.mark.anyio
async def test_hosted_buttons_page():
    r = readiness_of(await scan("hosted.html"))
    assert item(r, "sdk")["status"] == "partial"
    assert any("hosted" in e for e in item(r, "sdk")["evidence"])
    assert any(x["title"].startswith("Move from Hosted Buttons") for x in r["recommendations"])


@requires_browser
@pytest.mark.anyio
async def test_page_without_paypal():
    r = readiness_of(await scan("none.html"))
    assert r["score"] == 0 and not r["paypal_found"]


# --- A mock demo-store run stores the readiness ---

@requires_browser
@pytest.mark.anyio
async def test_demo_store_run_stores_paypal_readiness(server):  # noqa: F811
    run = await run_cassette(server, "day2_flaws_on", "on")
    pr = run["paypal_readiness"]
    assert pr is not None and pr["pages_scanned"]
    assert 0 <= pr["score"] <= 100
    assert {i["key"] for i in pr["checklist"]} == set(WEIGHTS)
    assert pr["steps_to_paypal"] != 0  # the demo store has no PayPal on the product page
    assert run["scorecard"]["total"] == 29  # the agent-readiness score is untouched
