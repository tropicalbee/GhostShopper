"""Failure types: every failed (or blocked) check carries one code. The code decides, deterministically,
who caused it (store vs buyer/environment) and which concrete fix the merchant sees.

The LLM may rephrase a fix for readability (agent/explain.py); it never chooses the fix or the cause.
"""

from dataclasses import dataclass

STORE, ENVIRONMENT = "store", "environment"


@dataclass(frozen=True)
class FailureType:
    code: str
    check: str
    cause: str  # store | environment
    fix: str


FAILURE_TYPES: dict[str, FailureType] = {
    f.code: f
    for f in (
        # discover / details
        FailureType("product_not_found", "product_found", STORE,
                    "Link the product from the home page with its full name as the link text (not just an image)."),
        FailureType("price_image_only", "price_in_text", STORE,
                    "Render the price as text, e.g. <span class=\"price\">$24.00</span>, instead of drawing it in an image."),
        FailureType("price_missing", "price_in_text", STORE,
                    "Show the price with its currency in the main product area, e.g. '$24.00'."),
        FailureType("jsonld_missing", "structured_data", STORE,
                    "Add a <script type=\"application/ld+json\"> Product block with name, sku, offers.price, "
                    "offers.priceCurrency and offers.availability."),
        FailureType("jsonld_incomplete", "structured_data", STORE,
                    "Complete the Product JSON-LD: add the missing fields listed in the evidence."),
        FailureType("stock_missing", "stock_readable", STORE,
                    "Say 'In stock' or 'Out of stock' in the page text and set offers.availability in JSON-LD."),
        FailureType("buy_button_nonsemantic", "clear_buy_button", STORE,
                    "Replace the clickable <div>s with one <button type=\"submit\">Buy now</button> (or 'Add to cart')."),
        FailureType("buy_button_missing", "clear_buy_button", STORE,
                    "Add one visible <button> labelled 'Buy now' or 'Add to cart' next to the price."),
        FailureType("currency_missing", "currency_stated", STORE,
                    "Write the currency next to every price ('$24.00', not '24.00') and set offers.priceCurrency "
                    "(e.g. \"USD\") in the Product JSON-LD."),
        FailureType("oos_still_buyable", "stock_consistent", STORE,
                    "When an item is sold out, remove or disable its buy button and block checkout for it."),
        FailureType("image_alt_missing", "image_alt_text", STORE,
                    "Set each product photo's alt text to the product name (e.g. alt=\"Speckled Stoneware Mug\"), "
                    "not a file name like IMG_0412.JPG."),
        FailureType("sale_claim_misleading", "sale_claim_consistent", STORE,
                    "Remove the 'was' price and discount badge, or make them match: the discount must equal "
                    "(was price - current price) / was price."),
        # checkout
        FailureType("buy_button_covered", "buy_button_unobstructed", STORE,
                    "Move the cookie banner (or any overlay) so it never covers the buy button, e.g. a slim bar "
                    "at the very bottom of the screen."),
        FailureType("price_changed_at_checkout", "price_consistent", STORE,
                    "Show and charge the same item price at checkout as on the product page; if there is a fee, "
                    "show it as its own line on the product page too."),
        FailureType("extra_form_step", "no_extra_steps", STORE,
                    "Remove the form between the product page and payment, or make its fields optional "
                    "and collect them after payment."),
        FailureType("checkout_not_reached", "checkout_reached", STORE,
                    "Make the buy button go straight to a checkout page that shows the PayPal button."),
        # payment
        FailureType("paypal_button_missing", "paypal_button_found", STORE,
                    "Render the PayPal button on checkout: load the PayPal JS SDK v6 with your client ID and show "
                    "<paypal-button> when PayPal is eligible."),
        FailureType("popup_not_opened", "popup_opened", STORE,
                    "Call session.start() directly inside the PayPal button's click handler, passing the "
                    "createOrder() promise without awaiting it first."),
        FailureType("popup_blocked_by_browser", "popup_opened", ENVIRONMENT,
                    "No store change needed: the shopper's browser blocked the PayPal window."),
        FailureType("approval_timeout", "payment_approved", ENVIRONMENT,
                    "No store change needed: the PayPal approval did not finish in time on PayPal's side."),
        FailureType("human_approval_timeout", "payment_approved", ENVIRONMENT,
                    "No store change needed: PayPal asked for a human check and nobody approved it in time."),
        FailureType("approval_cancelled", "payment_approved", ENVIRONMENT,
                    "No store change needed: the payment was cancelled in the PayPal window."),
        FailureType("capture_declined", "capture_completed", ENVIRONMENT,
                    "No store change needed: the buyer's funding source declined the payment."),
        FailureType("capture_error", "capture_completed", STORE,
                    "Fix the capture call on your server: POST /v2/checkout/orders/{id}/capture must succeed on "
                    "approval; check the error and debug_id in the evidence."),
        FailureType("capture_unconfirmed", "capture_completed", STORE,
                    "After capture, redirect to a confirmation page that shows the order number."),
        # verification
        FailureType("amount_mismatch", "payment_verified", STORE,
                    "Charge exactly the advertised price: build the PayPal order from the same price the product page shows."),
        FailureType("capture_amount_mismatch", "payment_verified", STORE,
                    "Capture the full order amount; the captured amount differs from the order you created."),
        FailureType("currency_mismatch", "payment_verified", STORE,
                    "Use the same currency on the product page, the PayPal order and the capture."),
        FailureType("order_capture_mismatch", "payment_verified", STORE,
                    "Store the capture id PayPal returns for this order; your records point to a different capture."),
        FailureType("capture_pending", "payment_verified", ENVIRONMENT,
                    "No store change needed: PayPal holds the capture as pending (e.g. review or eCheck)."),
        FailureType("fee_missing", "payment_verified", ENVIRONMENT,
                    "No store change needed: PayPal did not return a fee breakdown for this capture."),
        FailureType("fee_inconsistent", "payment_verified", ENVIRONMENT,
                    "No store change needed: PayPal's net amount does not equal gross minus fee; report it to PayPal."),
        FailureType("verification_unavailable", "payment_verified", ENVIRONMENT,
                    "No store change needed: GhostShopper's verification service could not be reached; rerun."),
        # outcome
        FailureType("agent_gave_up", "task_completed", STORE,
                    "Fix the failures above; the agent stopped because it could not find a way forward."),
        FailureType("agent_loop", "task_completed", STORE,
                    "Make each step's next action unambiguous; the agent kept repeating the same action."),
        FailureType("step_limit", "task_completed", STORE,
                    "Shorten the path to purchase; the agent ran out of steps."),
        FailureType("step_timeouts", "task_completed", STORE,
                    "Make pages respond faster; several steps timed out."),
        FailureType("payment_failed", "task_completed", STORE,
                    "Fix the payment failure above; the purchase did not complete."),
        FailureType("blocked_by_environment", "task_completed", ENVIRONMENT,
                    "No store change needed: the run stopped because of a problem outside the store."),
        FailureType("run_error", "task_completed", ENVIRONMENT,
                    "No store change needed: the test run itself failed (see the run error)."),
    )
}

# Failure codes used when a check never ran, by why it never ran.
NOT_TESTED_STORE = "not_tested"
NOT_TESTED_ENVIRONMENT = "blocked_by_environment"


def cause_of(code: str | None) -> str:
    """Unknown codes count as the store's fault: a failure is never waved away by default."""
    ft = FAILURE_TYPES.get(code or "")
    return ft.cause if ft else STORE


def fix_for(code: str | None) -> str | None:
    ft = FAILURE_TYPES.get(code or "")
    return ft.fix if ft else None


# PayPal capture issues that come from the buyer's side, not the merchant's integration.
BUYER_SIDE_CAPTURE_ISSUES = {
    "INSTRUMENT_DECLINED", "PAYER_ACTION_REQUIRED", "PAYER_CANNOT_PAY", "TRANSACTION_REFUSED",
    "REDIRECT_PAYER_FOR_ALTERNATE_FUNDING", "MAX_NUMBER_OF_PAYMENT_ATTEMPTS_EXCEEDED",
}
