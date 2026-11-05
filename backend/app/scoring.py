"""Deterministic agent-readiness score.

The score is a pure function of logged check outcomes. The LLM never influences it: it only
decides where the agent goes, and the checks are evaluated by code on what the browser saw.

Policy: only store-caused failures cost points. Outcomes that are not the store's fault (buyer's bank
declined, browser blocked a popup, a run error) are EXCLUDED, and the score is renormalized over the
points that remain: total = round(100 * earned / possible).
"""

from dataclasses import dataclass
from typing import Mapping

RULES_VERSION = "2026-11-05.3"

STAGES = ("discover", "details", "checkout", "payment", "outcome")

PASS, FAIL, NOT_TESTED, EXCLUDED = "pass", "fail", "not_tested", "excluded"
STATUSES = (PASS, FAIL, NOT_TESTED, EXCLUDED)


@dataclass(frozen=True)
class Check:
    key: str
    stage: str
    points: int
    severity: str  # critical | major | minor
    title: str
    fix: str  # generic; failure-specific fixes live in failures.FAILURE_TYPES


CHECKS: dict[str, Check] = {
    c.key: c
    for c in (
        Check("product_found", "discover", 5, "critical",
              "Agent found the product page",
              "Link every product from the home page with its full name as the link text."),
        Check("price_in_text", "details", 12, "critical",
              "Price is readable as text",
              "Show the price as text on the page, not only inside an image."),
        Check("currency_stated", "details", 3, "major",
              "Price states its currency",
              "Show the currency with the price ('$24.00') and set offers.priceCurrency in JSON-LD."),
        Check("structured_data", "details", 12, "major",
              "Product structured data (schema.org JSON-LD)",
              "Add Product JSON-LD with name, sku, offers.price, offers.priceCurrency and offers.availability."),
        Check("stock_readable", "details", 4, "minor",
              "Stock status is readable",
              "State availability in text (e.g. 'In stock') and in JSON-LD offers.availability."),
        Check("stock_consistent", "details", 3, "major",
              "Out-of-stock items cannot be bought",
              "Hide or disable the buy button when an item is sold out."),
        Check("image_alt_text", "details", 3, "minor",
              "Product photos have descriptive alt text",
              "Give every product photo an alt text that names the product."),
        Check("sale_claim_consistent", "details", 3, "major",
              "Sale claims add up",
              "Only show a 'was' price and a discount that match the real current price."),
        Check("clear_buy_button", "checkout", 10, "critical",
              "One clear, semantic buy button",
              "Use a real <button> or link labelled 'Buy now' or 'Add to cart'; remove unlabeled div buttons."),
        Check("buy_button_unobstructed", "checkout", 4, "major",
              "Buy button is not covered",
              "Keep banners and pop-ups from covering the buy button."),
        Check("no_extra_steps", "checkout", 6, "major",
              "No extra step before payment",
              "Remove forms between the product page and payment, or make their fields optional."),
        Check("checkout_reached", "checkout", 6, "critical",
              "Agent reached the checkout page",
              "Make sure the buy button leads straight to a checkout page with a payment button."),
        Check("price_consistent", "checkout", 4, "critical",
              "Checkout price matches the product page",
              "Show the same item price at checkout as on the product page; list any fees separately."),
        Check("paypal_button_found", "payment", 4, "critical",
              "PayPal button present and clickable",
              "Render the PayPal button on the checkout page and make sure PayPal is configured."),
        Check("popup_opened", "payment", 3, "major",
              "PayPal window opened",
              "Start PayPal checkout directly from the button click so the browser does not block the window."),
        Check("payment_approved", "payment", 3, "major",
              "Buyer could log in and approve",
              "Keep the PayPal flow standard; do not add steps or redirects around the approval."),
        Check("capture_completed", "payment", 5, "critical",
              "Payment captured and confirmed",
              "Capture the order on approval and show the order number on a confirmation page."),
        Check("payment_verified", "payment", 5, "critical",
              "Order, capture, amount and fees match",
              "Charge exactly the advertised price and capture the same amount you created the order for."),
        Check("task_completed", "outcome", 5, "major",
              "Agent completed the task without giving up",
              "Remove whatever made the agent stop: see the other failures in this run."),
    )
}
SEVERITY_ORDER = {"critical": 0, "major": 1, "minor": 2}


@dataclass(frozen=True)
class Fix:
    key: str
    stage: str
    severity: str
    points: int
    title: str
    fix: str
    status: str  # failed | not_tested


@dataclass(frozen=True)
class Excluded:
    key: str
    stage: str
    points: int
    title: str


@dataclass(frozen=True)
class Score:
    total: int  # 0-100 over `possible` points; 0 when possible == 0
    possible: int  # points the store could be judged on (100 minus excluded)
    stages: dict[str, tuple[int, int]]  # stage -> (earned, possible)
    fixes: list[Fix]
    excluded: list[Excluded]
    rules_version: str = RULES_VERSION


def _status(key: str, value: object) -> str:
    if value is True:
        return PASS
    if value is False:
        return FAIL
    if value is None:
        return NOT_TESTED
    if value in STATUSES:
        return value  # type: ignore[return-value]
    raise ValueError(f"Unknown status {value!r} for check {key}")


def compute_score(results: Mapping[str, object]) -> Score:
    """results maps check key -> True/PASS, False/FAIL, None/NOT_TESTED or EXCLUDED. Missing = not tested."""
    unknown = set(results) - set(CHECKS)
    if unknown:
        raise ValueError(f"Unknown check keys: {', '.join(sorted(unknown))}")
    status = {k: _status(k, results.get(k)) for k in CHECKS}

    earned = sum(c.points for k, c in CHECKS.items() if status[k] == PASS)
    possible = sum(c.points for k, c in CHECKS.items() if status[k] != EXCLUDED)
    total = (200 * earned + possible) // (2 * possible) if possible else 0  # round half up, integer-only

    stages = {
        stage: (
            sum(c.points for c in CHECKS.values() if c.stage == stage and status[c.key] == PASS),
            sum(c.points for c in CHECKS.values() if c.stage == stage and status[c.key] != EXCLUDED),
        )
        for stage in STAGES
    }
    fixes = [
        Fix(c.key, c.stage, c.severity, c.points, c.title, c.fix, "failed" if status[k] == FAIL else "not_tested")
        for k, c in CHECKS.items()
        if status[k] in (FAIL, NOT_TESTED)
    ]
    # Failed before untested; the outcome summary after the failures that caused it; then most points
    # recoverable, then severity. sorted() is stable, so ties keep registry order.
    fixes.sort(key=lambda f: (f.status != "failed", f.stage == "outcome", -f.points, SEVERITY_ORDER[f.severity]))
    excluded = [Excluded(c.key, c.stage, c.points, c.title) for k, c in CHECKS.items() if status[k] == EXCLUDED]
    return Score(total=total, possible=possible, stages=stages, fixes=fixes, excluded=excluded)
