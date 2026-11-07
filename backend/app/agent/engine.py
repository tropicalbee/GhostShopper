"""Applies the deterministic detectors to every page the agent lands on, and records check outcomes."""

from decimal import Decimal
from typing import Any, Awaitable, Callable, Protocol

from ..scoring import EXCLUDED, FAIL, PASS
from .. import feed
from . import checks
from .paypal_readiness import PayPalCollector, page_kind
from .platform import detect_platform
from .recorder import RunRecorder


class Screenshotter(Protocol):
    async def screenshot(self, name: str, full_page: bool = False) -> str: ...


PaypalProbe = Callable[[], Awaitable[dict[str, Any]]]


class CheckEngine:
    def __init__(self, recorder: RunRecorder, target_product: str | None, shots: Screenshotter,
                 live: bool = False, paypal_probe: PaypalProbe | None = None, budget: Decimal | None = None):
        self.rec = recorder
        self.target = target_product  # None on live stores: any product page counts
        self.shots = shots
        self.live = live
        self.paypal_probe = paypal_probe
        self.product_seen = False
        self.checkout_seen = False
        self.blocked = False  # the site's bot check stopped us
        self.platform_done = False
        self.paypal = PayPalCollector()
        self.checkout_url: str | None = None
        self.budget = budget  # the shopper's spending limit in USD; enforced here, never by the LLM
        self.checkout_total: Decimal | None = None
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
        if not self.platform_done and facts.get("platform_signals") is not None:
            # Keep looking until a page shows its platform (the first page may be an error or a redirect).
            detected = detect_platform(facts["platform_signals"])
            self.rec.set_platform(detected)
            self.platform_done = detected["platform"] != "unknown"
        if facts.get("paypal_signals") is not None and not facts.get("bot_check"):
            self.paypal.add(url, page_kind(url, checks.is_product_page(facts, self.target), checks.is_checkout_page(facts)),
                            facts["paypal_signals"])
        if facts.get("bot_check"):
            # A bot check is the site's choice, not a store defect: record it once and stop the run.
            if not self.blocked:
                self.blocked = True
                key = "product_found" if not self.product_seen else "checkout_reached"
                await self._record(checks.Outcome(
                    key, False, "This site blocked our check with a bot or security challenge. We didn't try to get past it.",
                    {"url": url, "title": facts.get("title")}, "site_blocked"), step_id)
            return
        if checks.is_product_page(facts, self.target):
            # Revisiting the product page restarts the path to checkout (wrong turns don't count as steps).
            self._form_pages = []
            if not self.product_seen:
                self.product_seen = True
                self.product_price = checks.first_price(facts)
                self.rec.set_product_snapshot(
                    feed.snapshot_from_facts(facts, checks._products_in_jsonld(facts.get("jsonld") or [])))
                await self._record(checks.Outcome("product_found", True, f"Reached '{facts.get('title')}'.",
                                                  {"url": url, "title": facts.get("title")}), step_id)
                for outcome in checks.evaluate_product_page(facts):
                    await self._record(outcome, step_id)
        elif checks.is_checkout_page(facts) and not self.checkout_seen:
            self.checkout_seen = True
            self.checkout_url = url
            self.checkout_total = checks.checkout_total(facts)
            await self._record(checks.Outcome("checkout_reached", True, f"Reached checkout: {facts.get('title')}.", {"url": url}), step_id)
            if self.product_seen:
                await self._record(checks.evaluate_path_to_checkout(url, self._form_pages), step_id)
                for outcome in checks.evaluate_checkout_prices(facts, self.product_price):
                    await self._record(outcome, step_id)
            if self.live and self.paypal_probe:
                await self.check_paypal(step_id)

    async def check_paypal(self, step_id: int | None) -> str:
        """Live stores: is the PayPal button present, visible and clickable? Never clicks it."""
        if self.rec.is_recorded("paypal_button_found"):
            row = next(r for r in self.rec.rows() if r["check_key"] == "paypal_button_found")
            return "The PayPal button was already checked: " + ("ready." if row["passed"] == 1 else "not usable.")
        state = await self.paypal_probe()
        ev = {k: state.get(k) for k in ("selector", "covered_by", "visible", "clickable", "disabled")}
        if state.get("found"):
            self.paypal.note_button(self.checkout_url, bool(state.get("visible")), state.get("selector"))
        if not state.get("found"):
            outcome = checks.Outcome("paypal_button_found", False, "No PayPal button on the cart or checkout page.",
                                     ev, "paypal_button_missing")
        elif not state.get("visible"):
            outcome = checks.Outcome("paypal_button_found", False, "A PayPal button is in the page but hidden.",
                                     ev, "paypal_button_hidden")
        elif not state.get("clickable"):
            why = f"covered by {state['covered_by']}" if state.get("covered_by") else "disabled"
            outcome = checks.Outcome("paypal_button_found", False, f"The PayPal button can't be clicked ({why}).",
                                     ev, "paypal_button_covered")
        else:
            outcome = checks.Outcome("paypal_button_found", True,
                                     "PayPal button present, visible and clickable. Not clicked: live stores are browse-only.", ev)
        await self._record(outcome, step_id)
        return outcome.reason

    async def stop_if_over_budget(self, facts: dict[str, Any], step_id: int | None = None) -> str | None:
        """Before any payment: None if the checkout total is within the spending limit (or there is none).
        Otherwise records the failed check, which is not the store's fault, and returns what to tell the shopper.
        A total we can't read is treated as over, because the limit can't be checked."""
        if self.budget is None:
            return None
        total = checks.checkout_total(facts)
        if total is not None and total <= self.budget:
            return None
        if total is None:
            reason = f"The checkout total could not be read, so it could not be checked against the ${self.budget} spending limit."
        else:
            reason = f"The checkout total ${total} is over the ${self.budget} spending limit, so the shopper did not pay."
        await self._record(checks.Outcome(
            "paypal_button_found", False, reason,
            {"url": facts.get("url"), "budget": str(self.budget), "checkout_total": str(total) if total is not None else None},
            "over_budget"), step_id)
        return f"Not paid: {reason}"

    async def stop_if_order_over_budget(self, amount: Decimal | None, facts: dict[str, Any],
                                        step_id: int | None = None) -> str | None:
        """The real check: the amount of the order the store just created, read from the backend response, not
        from page text. Called after the order exists but before anything is approved, so no money has moved.
        An amount we never saw is treated as over, because the limit can't be checked."""
        if self.budget is None or (amount is not None and amount <= self.budget):
            return None
        if amount is None:
            reason = f"The order amount could not be read, so it could not be checked against the ${self.budget} spending limit."
        else:
            reason = f"The order total ${amount} is over the ${self.budget} spending limit, so the shopper did not pay."
        page_total = checks.checkout_total(facts)
        await self._record(checks.Outcome(
            "paypal_button_found", False, reason,
            {"url": facts.get("url"), "budget": str(self.budget), "checkout_total": str(amount) if amount is not None else None,
             "page_total": str(page_total) if page_total is not None else None},
            "over_budget"), step_id)
        return f"Not paid: {reason}"

    def on_form_filled(self, facts: dict[str, Any]) -> None:
        """The agent had to fill a form. Counts as an extra step if it is between product and checkout."""
        if not self.product_seen or self.checkout_seen or checks.is_product_page(facts, self.target):
            return
        if any(p["url"] == facts.get("url") for p in self._form_pages):
            return
        form = (facts.get("forms") or [{}])[0]
        self._form_pages.append({"url": facts.get("url"), "selector": form.get("selector"), "fields": form.get("fields", [])})

    async def finalize(self, *, checkout: bool, end_reason: str, error: str | None = None) -> str:
        """Record goal checks and the task outcome, mark the rest untested, and return the run outcome.

        The outcome is decided from checks, never from what the LLM claimed in finish().
        """
        rec = self.rec
        rec.set_paypal_readiness(self.paypal.result())
        if error is None and not self.blocked:
            if not self.product_seen:
                what = f"a page for '{self.target}'" if self.target else "a product page"
                rec.record_check("product_found", False, f"The agent never reached {what}.", code="product_not_found")
            if not self.checkout_seen:
                rec.record_check("checkout_reached", False, "The agent never reached a checkout page.",
                                 code="checkout_not_reached")
            if self.live and self.checkout_seen and self.paypal_probe and not rec.is_recorded("paypal_button_found"):
                try:
                    await self.check_paypal(None)
                except Exception:  # browser gone; leave it untested rather than guess
                    pass
            if (checkout and self.checkout_seen and self.budget is not None and not rec.is_recorded("paypal_button_found")
                    and (self.checkout_total is None or self.checkout_total > self.budget)):
                # The shopper obeyed the limit and never tried to pay: say so, rather than blame the store.
                await self.stop_if_over_budget({"url": self.checkout_url, "prices": (
                    [{"value": str(self.checkout_total)}] if self.checkout_total is not None else [])})
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
        elif self.blocked:
            outcome, task = "blocked", (None, "site_blocked", "The site's bot check stopped the visit.")
        elif self.live and results.get("paypal_button_found") == PASS:
            outcome, task = "paypal_ready", (True, None, "Reached the PayPal button and checked it; live stores are browse-only.")
        elif self.live and results.get("paypal_button_found") == FAIL:
            outcome, task = "blocked", (False, "payment_failed", "Reached checkout but the PayPal button couldn't be used.")
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
        reasons = {
            "details": not_reached,
            "checkout": "Not tested: the agent never reached checkout." if self.product_seen else not_reached,
            "payment": ("Not tested: payment was not part of this run." if not checkout
                        else "Not tested: an earlier step stopped the payment."),
        }
        stage_codes = {}
        if self.live and not self.blocked and error is None:
            # Live stores are browse-only by design: the payment steps after the button are out of scope,
            # so they're excluded rather than scored as zero. The button itself is in scope.
            rec.record_check("paypal_button_found", None, "Not tested: the agent never reached the cart or checkout.",
                             code="not_tested")
            reasons["payment"] = "Not tested on live stores: GhostShopper only pays on its own demo store."
            stage_codes["payment"] = "live_store_browse_only"
        rec.mark_untested(reasons, blocked_by_environment=env_failure, stage_codes=stage_codes)
        return outcome


GAVE_UP_REASONS = {
    "agent_gave_up": "The agent gave up before finishing the task.",
    "agent_loop": "The agent kept repeating the same action on the same page and was stopped.",
    "step_limit": "The agent ran out of steps before finishing the task.",
    "step_timeouts": "Several steps timed out, so the run was stopped.",
}
