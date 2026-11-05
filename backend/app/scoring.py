"""Deterministic agent-readiness score.

The score is a pure function of logged check outcomes. The LLM never influences it: it only
decides where the agent goes, and the checks are evaluated by code on what the browser saw.
"""

from dataclasses import dataclass
from typing import Mapping

RULES_VERSION = "2026-11-05.1"

STAGES = ("discover", "details", "checkout", "payment")


@dataclass(frozen=True)
class Check:
    key: str
    stage: str
    points: int
    severity: str  # critical | major | minor
    title: str
    fix: str


CHECKS: dict[str, Check] = {
    c.key: c
    for c in (
        Check("product_found", "discover", 10, "critical",
              "Agent found the product page",
              "Link every product from the home page with its full name as the link text."),
        Check("price_in_text", "details", 15, "critical",
              "Price is readable as text",
              "Show the price as text on the page, not only inside an image."),
        Check("structured_data", "details", 15, "major",
              "Product structured data (schema.org JSON-LD)",
              "Add Product JSON-LD with name, sku, offers.price, offers.priceCurrency and offers.availability."),
        Check("stock_readable", "details", 5, "minor",
              "Stock status is readable",
              "State availability in text (e.g. 'In stock') and in JSON-LD offers.availability."),
        Check("clear_buy_button", "details", 15, "critical",
              "One clear, semantic buy button",
              "Use a real <button> or link labelled 'Buy now' or 'Add to cart'; remove unlabeled div buttons."),
        Check("no_extra_steps", "checkout", 10, "major",
              "No extra step before payment",
              "Remove forms between the product page and payment, or make their fields optional."),
        Check("checkout_reached", "checkout", 10, "critical",
              "Agent reached the checkout page",
              "Make sure the buy button leads straight to a checkout page with a payment button."),
        Check("paypal_button_found", "payment", 5, "critical",
              "PayPal button present and clickable",
              "Render the PayPal button on the checkout page and make sure PayPal is configured."),
        Check("popup_opened", "payment", 5, "major",
              "PayPal window opened",
              "Start PayPal checkout directly from the button click so the browser does not block the window."),
        Check("payment_approved", "payment", 5, "major",
              "Buyer could log in and approve",
              "Keep the PayPal flow standard; do not add steps or redirects around the approval."),
        Check("capture_completed", "payment", 5, "critical",
              "Payment captured and confirmed",
              "Capture the order on approval and show the order number on a confirmation page."),
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
class Score:
    total: int
    stages: dict[str, tuple[int, int]]  # stage -> (earned, possible)
    fixes: list[Fix]
    rules_version: str = RULES_VERSION


def compute_score(results: Mapping[str, bool | None]) -> Score:
    """results maps check key -> True (passed), False (failed), or None/missing (not tested)."""
    unknown = set(results) - set(CHECKS)
    if unknown:
        raise ValueError(f"Unknown check keys: {', '.join(sorted(unknown))}")
    total = sum(c.points for k, c in CHECKS.items() if results.get(k) is True)
    stages = {
        stage: (
            sum(c.points for c in CHECKS.values() if c.stage == stage and results.get(c.key) is True),
            sum(c.points for c in CHECKS.values() if c.stage == stage),
        )
        for stage in STAGES
    }
    fixes = [
        Fix(c.key, c.stage, c.severity, c.points, c.title, c.fix, "failed" if results.get(k) is False else "not_tested")
        for k, c in CHECKS.items()
        if results.get(k) is not True
    ]
    # Failed before untested, then most points recoverable, then severity. sorted() is stable,
    # so ties keep registry order.
    fixes.sort(key=lambda f: (f.status != "failed", -f.points, SEVERITY_ORDER[f.severity]))
    return Score(total=total, stages=stages, fixes=fixes)
