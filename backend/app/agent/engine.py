"""Applies the deterministic detectors to every page the agent lands on, and records check outcomes."""

from typing import Any, Protocol

from ..scoring import EXCLUDED, FAIL, PASS
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
        self.product_price = None  # first text price on the product page, for the checkout comparison
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
        self.rec.record_check(outcome.key, outcome.passed, outcome.reason, evidence, step_id, outcome.code)

    async def on_page(self, facts: dict[str, Any], step_id: int | None) -> None:
        url = facts.get("url")
        if checks.is_product_page(facts, self.target):
            # Revisiting the product page restarts the path to checkout (wrong turns don't count as steps).
            self._form_pages = []
            if not self.product_seen:
                self.product_seen = True
                self.product_price = checks.first_price(facts)
                await self._record(checks.Outcome("product_found", True, f"Reached '{facts.get('title')}'.", {"url": url}), step_id)
                for outcome in checks.evaluate_product_page(facts):
                    await self._record(outcome, step_id)
        elif checks.is_checkout_page(facts) and not self.checkout_seen:
            self.checkout_seen = True
            self.checkout_url = url
            await self._record(checks.Outcome("checkout_reached", True, f"Reached checkout: {facts.get('title')}.", {"url": url}), step_id)
            if self.product_seen:
                await self._record(checks.evaluate_path_to_checkout(url, self._form_pages), step_id)
                for outcome in checks.evaluate_checkout_prices(facts, self.product_price):
                    await self._record(outcome, step_id)

    def on_form_filled(self, facts: dict[str, Any]) -> None:
        """The agent had to fill a form. Counts as an extra step if it is between product and checkout."""
        if not self.product_seen or self.checkout_seen or checks.is_product_page(facts, self.target):
            return
        if any(p["url"] == facts.get("url") for p in self._form_pages):
            return
        form = (facts.get("forms") or [{}])[0]
        self._form_pages.append({"url": facts.get("url"), "selector": form.get("selector"), "fields": form.get("fields", [])})

    def finalize(self, *, checkout: bool, end_reason: str, error: str | None = None) -> str:
        """Record goal checks and the task outcome, mark the rest untested, and return the run outcome.

        The outcome is decided from checks, never from what the LLM claimed in finish().
        """
        rec = self.rec
        if error is None:
            if not self.product_seen:
                rec.record_check("product_found", False, f"The agent never reached a page for '{self.target}'.",
                                 code="product_not_found")
            if not self.checkout_seen:
                rec.record_check("checkout_reached", False, "The agent never reached a checkout page.",
                                 code="checkout_not_reached")
            if checkout and self.checkout_seen and not rec.has_environment_failure():
                rec.record_check("paypal_button_found", False,
                                 "The agent reached checkout but never started the PayPal payment.",
                                 code="paypal_button_missing")
        results = rec.results()
        env_failure = error is not None or rec.has_environment_failure()
        payment_keys = ("paypal_button_found", "popup_opened", "payment_approved", "capture_completed", "payment_verified")
        payment_attempted = any(results.get(k) in (FAIL, EXCLUDED) for k in payment_keys)

        if error is not None:
            outcome, task = "error", (None, "run_error", f"The run failed: {error}")
        elif checkout and results.get("capture_completed") == PASS:
            outcome, task = "purchased", (True, None, "Purchase completed and captured.")
        elif not checkout and results.get("checkout_reached") == PASS:
            outcome, task = "reached_checkout", (True, None, "Reached checkout, which was this run's goal.")
        elif checkout and payment_attempted:
            outcome = "blocked"
            task = ((None if env_failure else False),
                    "blocked_by_environment" if env_failure else "payment_failed",
                    "The payment did not complete" + (" for a reason outside the store." if env_failure else "."))
        else:
            outcome = "gave_up"
            code = {"agent_loop": "agent_loop", "step_limit": "step_limit",
                    "step_timeouts": "step_timeouts"}.get(end_reason, "agent_gave_up")
            task = (False, code, GAVE_UP_REASONS.get(code, "The agent stopped before finishing the task."))
        passed, code, reason = task
        rec.record_check("task_completed", passed, reason, {"end_reason": end_reason}, code=code)

        not_reached = "Not tested: the agent never reached the product page."
        rec.mark_untested({
            "details": not_reached,
            "checkout": "Not tested: the agent never reached checkout." if self.product_seen else not_reached,
            "payment": ("Not tested: payment was not part of this run." if not checkout
                        else "Not tested: an earlier step stopped the payment."),
        }, blocked_by_environment=env_failure)
        return outcome


GAVE_UP_REASONS = {
    "agent_gave_up": "The agent gave up before finishing the task.",
    "agent_loop": "The agent kept repeating the same action on the same page and was stopped.",
    "step_limit": "The agent ran out of steps before finishing the task.",
    "step_timeouts": "Several steps timed out, so the run was stopped.",
}
