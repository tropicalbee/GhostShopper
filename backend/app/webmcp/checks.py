"""Deterministic checks on how well a store's WebMCP tools worked in one run. A checklist, not a score: computed
from the run's recorded webmcp data by code (never an LLM), and it never touches the readiness score."""

from decimal import Decimal, InvalidOperation
from typing import Any

from .tools import COMPLETE, INITIATE, SEARCH, SHOPPING_TOOLS

PASS, FAIL, NOT_TESTED = "pass", "fail", "not_tested"
CHECKOUT_TOOLS = (INITIATE, COMPLETE)


def _check(key: str, label: str, status: str, evidence: str) -> dict[str, str]:
    return {"key": key, "label": label, "status": status, "evidence": evidence}


def _same(a: str, b: str) -> bool:
    try:
        return Decimal(a) == Decimal(b)
    except (InvalidOperation, TypeError):
        return False


def tool_checks(report: dict[str, Any], *, trace: dict[str, Any] | None, catalog_price: dict[str, str] | None,
                external: bool, mock_paypal: bool) -> list[dict[str, str]]:
    """report: the run's webmcp JSON. trace: the run's purchase trace. catalog_price: the demo catalog price of the
    target ({"amount", "currency"}), None on the showcase."""
    tools = {t["name"]: t for t in (report.get("discovery") or {}).get("tools", [])}
    hand, done = report.get("handoff"), report.get("completion")
    prices = report.get("price_consistency") or {}
    unit = prices.get("unit_prices") or {}
    out = []

    found = [t for t in SHOPPING_TOOLS if t in tools]
    out.append(_check("tools_discovered", "The shopping tools are registered",
                      PASS if len(found) == len(SHOPPING_TOOLS) else FAIL,
                      f"Found {', '.join(found) or 'none'}" + (f"; missing {', '.join(t for t in SHOPPING_TOOLS if t not in tools)}" if len(found) < 4 else "")))

    bad = [name for name, t in tools.items()
           if not (name and t.get("description") and (t.get("input_schema") or {}).get("type") == "object")
           or (name in CHECKOUT_TOOLS and t.get("read_only"))]
    out.append(_check("schemas_valid", "Every tool has a name, description and object schema; checkout tools are not read-only",
                      NOT_TESTED if not tools else FAIL if bad else PASS,
                      "No tools were discovered" if not tools else f"Problems with {', '.join(bad)}" if bad else f"{len(tools)} tool(s) checked"))

    out.append(_product_found(report, external))

    known = {k: v for k, v in unit.items() if v is not None}
    if len(known) < 2:
        status, why = NOT_TESTED, "Fewer than two tool results quoted a readable price"
    else:
        same = len(set(known.values())) == 1
        on_catalog = catalog_price is None or all(_same(v, catalog_price["amount"]) for v in known.values())
        status = PASS if same and on_catalog else FAIL
        why = ", ".join(f"{k} {v}" for k, v in known.items()) + (f"; catalog {catalog_price['amount']}" if catalog_price else "")
    out.append(_check("price_consistent", "The price agrees across search, product, checkout and capture", status, why))

    if hand is None:
        out.append(_check("buyer_approval_required", "Payment waits for the buyer's approval", NOT_TESTED, "Checkout was never started"))
    else:
        early = done is not None and not hand.get("approved")
        out.append(_check("buyer_approval_required", "Payment waits for the buyer's approval", FAIL if early else PASS,
                          "Money was captured without the buyer's approval" if early
                          else "initiateCheckout returned an approval_url and nothing was captured before the buyer approved"))

    if hand is None:
        out.append(_check("handoff_to_paypal", "Checkout hands the buyer to PayPal", NOT_TESTED, "Checkout was never started"))
    else:
        host = hand.get("approval_url_host") or ""
        paypal = host == "paypal.com" or host.endswith(".paypal.com")
        out.append(_check("handoff_to_paypal", "Checkout hands the buyer to PayPal", PASS if paypal or mock_paypal else FAIL,
                          f"Approval link host: {host}" + (" (the mock PayPal, not PayPal)" if mock_paypal and not paypal else "")))

    captured = bool(done) and (bool(done.get("capture_id")) or str(done.get("status") or "").upper() == "COMPLETED")
    out.append(_check("checkout_completed", "completeCheckout returned a completed capture",
                      PASS if captured else NOT_TESTED if done is None else FAIL,
                      f"Capture {done.get('capture_id') or done.get('status')}" if captured
                      else "completeCheckout was never called" if done is None else f"Status {done.get('status')}, no capture"))

    if external:
        out.append(_check("order_recorded", "The store's order record agrees with the capture", NOT_TESTED,
                          "PayPal's showcase is PayPal's merchant: there is no store order to read back"))
    elif trace is None or not captured:
        out.append(_check("order_recorded", "The store's order record agrees with the capture", NOT_TESTED, "No capture to compare with"))
    else:
        first = trace.get("first_mismatch")
        says = next(s for s in trace["stages"] if s["key"] == "store_says")["cells"]["status"]
        out.append(_check("order_recorded", "The store's order record agrees with the capture",
                          FAIL if first else NOT_TESTED if says["kind"] != "known" else PASS,
                          f"First mismatch at {first['stage']}: {first['field']} was {first['actual']}" if first
                          else "The store order page was not read back" if says["kind"] != "known"
                          else f"Store order, PayPal records and the order page agree ({says['value']})"))
    return out


def _product_found(report: dict[str, Any], external: bool) -> dict[str, str]:
    """The product the agent checked out appears in a searchProducts result (on the showcase the target is generic and
    titles are brand names, so that is the test); on the demo store its title must also match the target."""
    label = "searchProducts returned the product that was bought"
    search = report.get("search") or {}
    if SEARCH not in {c["tool"] for c in report.get("tool_calls", [])}:
        return _check("product_found", label, NOT_TESTED, "searchProducts was never called")
    bought = report.get("bought")
    if not bought:  # no checkout: all that can be said is whether the target came back
        found = bool(search.get("matched"))
        return _check("product_found", label, PASS if found else FAIL,
                      f"{search.get('count', 0)} product(s) returned" + ("" if found else ", none matching the target"))
    pid, title = bought["product_id"], bought.get("title") or ""
    listed = pid in (search.get("products") or {})
    named = f'"{title}" ({pid})' if title else f"product {pid}"
    if not listed:
        return _check("product_found", label, FAIL, f"{named} was checked out but never appeared in a search result")
    target = str(report.get("target") or "")
    if not external and target.lower() not in title.lower():
        return _check("product_found", label, FAIL, f'Bought {named}, which does not match the target "{target}"')
    return _check("product_found", label, PASS, f"Bought {named}, listed in a search result")
