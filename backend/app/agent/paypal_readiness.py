"""How ready a store's PayPal setup is for AI shopping agents, read from the pages the agent visited.

Pure and deterministic: the browser collects raw page signals (browser.FACTS_JS, `paypal_signals`), this
module turns them into a checklist, recommendations and a 0-100 "PayPal readiness" figure. The LLM is never
involved. This figure is separate from the agent-readiness score and does not change it.

Weights (fixed, sum to 100):
  button     20  a PayPal button is on a page and visible (8 if it is in the page but hidden)
  sdk        20  PayPal JS SDK v6 (8 for v5 or Hosted Buttons: older integrations)
  express    18  steps from the product page to the first visible PayPal button: 0 steps 18, 1 step 12, 2 steps 6
  messaging  12  Pay Later messaging element on a page (6 when only the SDK component is loaded)
  paylater    5  a Pay Later button
  venmo      10  a Venmo button (5 when Venmo is only enabled in the SDK settings: not confirmed visible)
  card       15  card or guest checkout offered (card fields component or "debit or credit card" text)
"""

import re
from typing import Any
from urllib.parse import parse_qs, urlparse

VERSION = "1"
WEIGHTS = {"button": 20, "sdk": 20, "express": 18, "messaging": 12, "paylater": 5, "venmo": 10, "card": 15}
assert sum(WEIGHTS.values()) == 100

DOCS = {
    "v6": "https://developer.paypal.com/docsai/payments/methods/paypal/sdk/js/v6/paypal-checkout",
    "upgrade": "https://developer.paypal.com/v5-v6",
    "checkout": "https://developer.paypal.com/docs/checkout/",
    "paylater": "https://developer.paypal.com/docs/checkout/pay-later/us/",
    "venmo": "https://developer.paypal.com/docs/checkout/pay-with-venmo/",
    "card": "https://developer.paypal.com/docs/checkout/advanced/",
}

SDK_V6_RE = re.compile(r"paypal\.com/web-sdk/v6/", re.I)
SDK_MOCK_RE = re.compile(r"/mock-paypal/sdk\.js", re.I)  # the practice-run stand-in for the v6 SDK
SDK_V5_RE = re.compile(r"paypal\.com/sdk/js", re.I)
CART_RE = re.compile(r"/(cart|basket|bag)(/|$|\?)", re.I)
CARD_TEXT_RE = re.compile(r"debit or credit card|pay with (a )?(debit |credit )?card", re.I)


def page_kind(url: str, is_product: bool, is_checkout: bool) -> str:
    """product | cart | checkout | other, from the checks' own page detectors plus the cart path."""
    if is_product:
        return "product"
    path = urlparse(url or "").path
    if CART_RE.search(path + "/") and "checkout" not in path.lower():
        return "cart"
    return "checkout" if is_checkout else "other"


def _split(value: str | None) -> list[str]:
    return [p.strip().lower() for p in (value or "").split(",") if p.strip()]


def parse_sdk(scripts: list[str]) -> dict[str, Any] | None:
    """The PayPal SDK a page loads: version, source URL (no client id) and the v5 query parameters."""
    for src in scripts or []:
        if SDK_V6_RE.search(src) or SDK_MOCK_RE.search(src):
            mock = bool(SDK_MOCK_RE.search(src))
            return {"version": "v6", "src": src.split("?")[0], "mock": mock, "components": [], "enable_funding": [],
                    "disable_funding": [], "currency": None, "intent": None}
    for src in scripts or []:
        if SDK_V5_RE.search(src):
            q = {k.lower(): v[0] for k, v in parse_qs(urlparse(src).query).items() if v}
            return {"version": "v5", "src": src.split("?")[0], "mock": False, "components": _split(q.get("components")),
                    "enable_funding": _split(q.get("enable-funding")), "disable_funding": _split(q.get("disable-funding")),
                    "currency": q.get("currency"), "intent": q.get("intent")}
    return None


def normalize(raw: dict[str, Any] | None) -> dict[str, Any]:
    """Raw browser signals for one page -> flags and evidence strings."""
    raw = raw or {}
    scripts = raw.get("scripts") or []
    tags = raw.get("elements") or []  # [{tag, visible, text}]
    globals_ = set(raw.get("globals") or [])
    funding = set(raw.get("funding_sources") or [])
    sdk = parse_sdk(scripts)
    if sdk is None and "createInstance" in globals_:
        sdk = {"version": "v6", "src": None, "mock": False, "components": [], "enable_funding": [],
               "disable_funding": [], "currency": None, "intent": None}
    elif sdk is None and ("Buttons" in globals_ or "Messages" in globals_):
        sdk = {"version": "v5", "src": None, "mock": False, "components": [], "enable_funding": [],
               "disable_funding": [], "currency": None, "intent": None}

    def tag_has(word: str) -> list[dict[str, Any]]:
        return [t for t in tags if word in t["tag"]]

    pay_later_tags = tag_has("pay-later")
    venmo_tags = tag_has("venmo")
    message_tags = [t for t in tag_has("message")]
    card_tags = [t for t in tags if "card" in t["tag"]]
    buttons = raw.get("buttons") or []  # [{selector, visible}]
    comps = sdk["components"] if sdk else []

    evidence: dict[str, list[str]] = {}
    if buttons:
        evidence["button"] = [f"{b['selector']} ({'visible' if b['visible'] else 'hidden'})" for b in buttons[:3]]
    if sdk:
        ev = [f"{sdk['version']} SDK: {sdk['src']}" if sdk["src"] else f"{sdk['version']} SDK (window.paypal)"]
        if sdk["mock"]:
            ev.append("practice run: the scripted PayPal stand-in")
        if sdk["version"] == "v5":
            for label, val in (("components", ",".join(sdk["components"])), ("enable-funding", ",".join(sdk["enable_funding"])),
                               ("disable-funding", ",".join(sdk["disable_funding"])), ("currency", sdk["currency"]),
                               ("intent", sdk["intent"])):
                if val:
                    ev.append(f"{label}={val}")
        evidence["sdk"] = ev
    if message_tags:
        evidence["messaging"] = [f"<{t['tag']}>" for t in message_tags[:2]]
    if raw.get("pp_message_count"):
        evidence.setdefault("messaging", []).append(f"{raw['pp_message_count']} element(s) with data-pp-message")
    if "Messages" in globals_:
        evidence.setdefault("messaging_sdk", []).append("paypal.Messages is loaded")
    if "messages" in comps:
        evidence.setdefault("messaging_sdk", []).append("components includes messages")
    if pay_later_tags:
        evidence["paylater"] = [f"<{t['tag']}>" for t in pay_later_tags[:2]]
    if "paylater" in funding:
        evidence.setdefault("paylater", []).append('data-funding-source="paylater"')
    if venmo_tags:
        evidence["venmo"] = [f"<{t['tag']}>" for t in venmo_tags[:2]]
    if "venmo" in funding:
        evidence.setdefault("venmo", []).append('data-funding-source="venmo"')
    if sdk and "venmo" in sdk["enable_funding"]:
        evidence["venmo_config"] = ["enable-funding includes venmo"]
    card_ev: list[str] = []
    if any("card-fields" in c or c == "card" for c in comps):
        card_ev.append("components includes card-fields")
    if card_tags:
        card_ev.append(f"<{card_tags[0]['tag']}>")
    if "card" in funding:
        card_ev.append('data-funding-source="card"')
    if raw.get("card_text"):
        card_ev.append(f'text: "{raw["card_text"]}"')
    if card_ev:
        evidence["card"] = card_ev
    hosted = "hosted-buttons" in comps or "HostedButtons" in globals_
    if hosted:
        evidence["hosted"] = ["components includes hosted-buttons" if "hosted-buttons" in comps else "paypal.HostedButtons is loaded"]

    return {
        "sdk": sdk,
        "hosted": hosted,
        "has_button": bool(buttons),
        "button_visible": any(b["visible"] for b in buttons),
        "messaging": bool(message_tags or raw.get("pp_message_count")),
        "messaging_sdk": "messaging_sdk" in evidence,
        "paylater": bool(pay_later_tags or "paylater" in funding),
        "venmo": bool(venmo_tags or "venmo" in funding),
        "venmo_config": "venmo_config" in evidence,
        "card": bool(card_ev),
        "evidence": evidence,
    }


class PayPalCollector:
    """Accumulates the pages the agent visits, in order, then builds the readiness result."""

    def __init__(self) -> None:
        self.pages: list[dict[str, Any]] = []  # distinct urls in first-visit order

    def add(self, url: str, kind: str, raw: dict[str, Any] | None) -> None:
        sig = normalize(raw)
        for p in self.pages:
            if p["url"] == url:
                p["kind"] = p["kind"] if p["kind"] != "other" else kind
                for k in ("has_button", "button_visible", "messaging", "messaging_sdk", "paylater", "venmo",
                          "venmo_config", "card", "hosted"):
                    p[k] = p[k] or sig[k]
                p["sdk"] = p["sdk"] or sig["sdk"]
                for k, v in sig["evidence"].items():
                    p["evidence"].setdefault(k, v)
                return
        self.pages.append({"url": url, "kind": kind, **sig})

    def note_button(self, url: str | None, visible: bool, selector: str | None) -> None:
        """The live-store button probe saw the button; trust it over the earlier page scan."""
        for p in self.pages:
            if p["url"] == url:
                p["has_button"] = True
                p["button_visible"] = p["button_visible"] or bool(visible)
                p["evidence"].setdefault("button", [f"{selector} ({'visible' if visible else 'hidden'})"])

    def result(self) -> dict[str, Any] | None:
        return build_readiness(self.pages)


def _item(key: str, label: str, status: str, points: int, evidence: list[str], note: str) -> dict[str, Any]:
    return {"key": key, "label": label, "status": status, "points": points, "max": WEIGHTS[key],
            "evidence": evidence, "note": note}


def build_readiness(pages: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not pages:
        return None

    def anywhere(flag: str) -> bool:
        return any(p[flag] for p in pages)

    def ev(key: str) -> list[str]:
        out: list[str] = []
        for p in pages:
            for line in p["evidence"].get(key, []):
                if line not in out:
                    out.append(line)
        return out[:4]

    sdk = next((p["sdk"] for p in pages if p["sdk"] and p["sdk"]["version"] == "v6"), None) or \
        next((p["sdk"] for p in pages if p["sdk"]), None)
    hosted = anywhere("hosted")
    has_button, button_visible = anywhere("has_button"), anywhere("button_visible")

    # Steps from the first product page to the first page with a visible PayPal button.
    first_product = next((i for i, p in enumerate(pages) if p["kind"] == "product"), None)
    first_button = next((i for i, p in enumerate(pages) if p["button_visible"]), None)
    steps = None if first_button is None or first_product is None else max(0, first_button - first_product)
    by_kind = {k: any(p["button_visible"] for p in pages if p["kind"] == k) for k in ("product", "cart", "checkout")}

    items: list[dict[str, Any]] = []
    if button_visible:
        items.append(_item("button", "PayPal button", "detected", 20, ev("button"), "A visible PayPal button was found."))
    elif has_button:
        items.append(_item("button", "PayPal button", "partial", 8, ev("button"),
                           "A PayPal button is in the page but was hidden when the agent looked."))
    else:
        items.append(_item("button", "PayPal button", "missing", 0, [], "No PayPal button on the pages the agent visited."))

    if sdk and sdk["version"] == "v6":
        items.append(_item("sdk", "PayPal JS SDK v6", "detected", 20, ev("sdk"), "The store uses the current v6 Web SDK."))
    elif sdk or hosted:
        which = "Hosted Buttons" if hosted and not sdk else f"SDK {sdk['version']}"
        items.append(_item("sdk", "PayPal JS SDK v6", "partial", 8, ev("sdk") + ev("hosted"),
                           f"The store uses an older integration ({which})."))
    else:
        items.append(_item("sdk", "PayPal JS SDK v6", "missing", 0, [], "No PayPal SDK script was found."))

    if steps is None:
        why = ("No visible PayPal button was reached." if first_button is None
               else "The agent never reached a product page, so the distance can't be measured.")
        items.append(_item("express", "PayPal early in the path", "missing" if first_button is None else "not_confirmed",
                           0, [], why))
    else:
        pts = {0: 18, 1: 12, 2: 6}.get(steps, 0)
        where = next((k for k in ("product", "cart", "checkout") if by_kind[k] and
                      pages[first_button]["kind"] == k), pages[first_button]["kind"])
        note = ("PayPal is on the product page itself." if steps == 0
                else f"PayPal first appears {steps} page{'s' if steps != 1 else ''} after the product page, on the {where} page.")
        items.append(_item("express", "PayPal early in the path", "detected" if steps == 0 else "partial" if pts else "missing",
                           pts, [f"first PayPal button: {pages[first_button]['url']}", f"page steps from product: {steps}"], note))

    if anywhere("messaging"):
        items.append(_item("messaging", "Pay Later messaging", "detected", 12, ev("messaging"), "Pay Later messaging is shown."))
    elif anywhere("messaging_sdk"):
        items.append(_item("messaging", "Pay Later messaging", "not_confirmed", 6, ev("messaging_sdk"),
                           "The messaging component is loaded but no message was seen on the page."))
    else:
        items.append(_item("messaging", "Pay Later messaging", "missing", 0, [], "No Pay Later messaging found."))

    if anywhere("paylater"):
        items.append(_item("paylater", "Pay Later button", "detected", 5, ev("paylater"), "A Pay Later button is offered."))
    else:
        items.append(_item("paylater", "Pay Later button", "missing", 0, [], "No Pay Later button found."))

    if anywhere("venmo"):
        items.append(_item("venmo", "Venmo", "detected", 10, ev("venmo"), "A Venmo button is on the page."))
    elif anywhere("venmo_config"):
        items.append(_item("venmo", "Venmo", "not_confirmed", 5, ev("venmo_config"),
                           "Venmo is enabled in the SDK settings, but no Venmo button was seen. Venmo only shows for eligible US buyers, so this is not confirmed."))
    else:
        items.append(_item("venmo", "Venmo", "missing", 0, [], "No sign of Venmo."))

    if anywhere("card"):
        items.append(_item("card", "Card or guest checkout", "detected", 15, ev("card"), "Buyers can pay by card without a PayPal account."))
    else:
        items.append(_item("card", "Card or guest checkout", "missing", 0, [], "No sign of card or guest checkout."))

    score = sum(i["points"] for i in items)
    paypal_found = bool(sdk or hosted or has_button)
    if not paypal_found:
        score = 0
    recs = recommendations(items, sdk, hosted, steps, paypal_found)
    return {
        "version": VERSION, "score": score, "paypal_found": paypal_found,
        "status": "good" if score >= 80 else "warn" if score >= 50 else "bad",
        "sdk": sdk, "steps_to_paypal": steps, "placement": by_kind,
        "pages_scanned": [{"url": p["url"], "kind": p["kind"], "button": p["button_visible"]} for p in pages],
        "checklist": items, "recommendations": recs,
    }


def recommendations(items: list[dict[str, Any]], sdk: dict[str, Any] | None, hosted: bool, steps: int | None,
                    paypal_found: bool) -> list[dict[str, Any]]:
    by = {i["key"]: i for i in items}
    out: list[dict[str, Any]] = []

    def add(key: str, title: str, why: str, url: str) -> None:
        item = by[key]
        out.append({"key": key, "title": title, "why": why, "docs_url": url, "points": item["max"] - item["points"]})

    if not paypal_found:
        out.append({"key": "add_paypal", "title": "Add PayPal checkout with the v6 Web SDK",
                    "why": "No PayPal was found, so an AI shopper has no PayPal way to pay.",
                    "docs_url": DOCS["v6"], "points": 100})
        return out
    if by["button"]["status"] != "detected":
        add("button", "Make the PayPal button visible",
            "A hidden or missing button cannot be found or clicked by an AI shopper.", DOCS["v6"])
    if by["sdk"]["status"] != "detected":
        title = "Move from Hosted Buttons to the v6 Web SDK" if hosted else "Upgrade JS SDK v5 to v6"
        add("sdk", title, "v6 is PayPal's current SDK and the one its newer buyer and agent features build on.", DOCS["upgrade"])
    if by["express"]["points"] < by["express"]["max"]:
        add("express", "Offer PayPal on the product page (express) so agents reach payment in fewer steps",
            "Every extra page between the product and the PayPal button is a place an agent can give up.", DOCS["checkout"])
    if by["messaging"]["status"] != "detected":
        add("messaging", "Add Pay Later messaging on the product page",
            "Pay installment offers next to the price lift conversion and give agents a clear payment option.", DOCS["paylater"])
    if by["paylater"]["status"] != "detected":
        add("paylater", "Add a Pay Later button", "Lets buyers split the payment at checkout.", DOCS["paylater"])
    if by["venmo"]["status"] == "missing":
        add("venmo", "Enable Venmo for US buyers", "Venmo is a popular way to pay for US buyers on mobile.", DOCS["venmo"])
    elif by["venmo"]["status"] == "not_confirmed":
        add("venmo", "Confirm Venmo shows for US buyers",
            "It is enabled in settings, but we could not see the button from here.", DOCS["venmo"])
    if by["card"]["status"] != "detected":
        add("card", "Offer card payment without a PayPal account (guest checkout)",
            "Buyers and agents without a PayPal login can still pay.", DOCS["card"])
    out.sort(key=lambda r: -r["points"])
    return out
