"""Applies the deterministic detectors to every page the agent lands on, and records check outcomes."""

from typing import Any, Protocol

from . import checks
from .recorder import RunRecorder


class Screenshotter(Protocol):
    async def screenshot(self, name: str, full_page: bool = False) -> str: ...


class CheckEngine:
    def __init__(self, recorder: RunRecorder, target_product: str, shots: Screenshotter):
        self.rec = recorder
        self.target = target_product
        self.shots = shots
        self.product_seen = False
        self.checkout_seen = False
        self.checkout_url: str | None = None
        self._form_pages: list[dict[str, Any]] = []

    async def _record(self, outcome: checks.Outcome, step_id: int | None) -> None:
        if self.rec.is_recorded(outcome.key):
            return
        evidence = dict(outcome.evidence)
        if not outcome.passed:
            try:
                evidence["screenshot"] = await self.shots.screenshot(f"check-{outcome.key}", full_page=True)
            except Exception as exc:  # evidence is best-effort; the check outcome is what counts
                evidence["screenshot_error"] = str(exc)[:200]
        self.rec.record_check(outcome.key, outcome.passed, outcome.reason, evidence, step_id)

    async def on_page(self, facts: dict[str, Any], step_id: int | None) -> None:
        url = facts.get("url")
        if checks.is_product_page(facts, self.target):
            # Revisiting the product page restarts the path to checkout (wrong turns don't count as steps).
            self._form_pages = []
            if not self.product_seen:
                self.product_seen = True
                await self._record(checks.Outcome("product_found", True, f"Reached '{facts.get('title')}'.", {"url": url}), step_id)
                for outcome in checks.evaluate_product_page(facts):
                    await self._record(outcome, step_id)
        elif checks.is_checkout_page(facts) and not self.checkout_seen:
            self.checkout_seen = True
            self.checkout_url = url
            await self._record(checks.Outcome("checkout_reached", True, f"Reached checkout: {facts.get('title')}.", {"url": url}), step_id)
            if self.product_seen:
                await self._record(checks.evaluate_path_to_checkout(url, self._form_pages), step_id)

    def on_form_filled(self, facts: dict[str, Any]) -> None:
        """The agent had to fill a form. Counts as an extra step if it is between product and checkout."""
        if not self.product_seen or self.checkout_seen or checks.is_product_page(facts, self.target):
            return
        if any(p["url"] == facts.get("url") for p in self._form_pages):
            return
        form = (facts.get("forms") or [{}])[0]
        self._form_pages.append({"url": facts.get("url"), "selector": form.get("selector"), "fields": form.get("fields", [])})

    def finalize(self, *, checkout: bool) -> None:
        if not self.product_seen:
            self.rec.record_check("product_found", False, f"The agent never reached a page for '{self.target}'.")
        if not self.checkout_seen:
            self.rec.record_check("checkout_reached", False, "The agent never reached a checkout page.")
        if checkout and self.checkout_seen:
            self.rec.record_check("paypal_button_found", False, "The agent reached checkout but never started the PayPal payment.")
        not_reached = "Not tested: the agent never reached the product page."
        self.rec.mark_untested({
            "details": not_reached,
            "checkout": "Not tested: the agent never reached checkout." if self.product_seen else not_reached,
            "payment": ("Not tested: payment was not part of this run." if not checkout
                        else "Not tested: an earlier payment step failed."),
        })
