"""Plain English for shopkeepers: what went wrong, why it costs sales, how to fix it (with platform
steps when we know the platform), the step-by-step narration, and the traffic-light status.

No jargon here: never JSON-LD, selector or DOM. The technical fix stays in failures.FAILURE_TYPES
for the Advanced view and the developer summary.
"""

import re
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class Plain:
    title: str  # what's wrong, as the shopkeeper sees it
    why: str  # why it costs sales, one sentence
    how: str  # how to fix it, any platform
    steps: dict[str, str] = field(default_factory=dict)  # platform -> steps


PLAIN: dict[str, Plain] = {
    "product_not_found": Plain(
        "AI shoppers can't find your product from the home page",
        "If a shopping assistant can't find the product, it can't recommend or buy it.",
        "Link each product from your home page using its full name, not just a picture.",
        {"shopify": "In Shopify: Online Store > Themes > Customize, add a Featured collection or Featured product section to the home page.",
         "wix": "In Wix: open the Editor, add a Product Gallery or Featured Products section to your home page.",
         "woocommerce": "In WordPress: edit your home page and add the Products or Featured Products block."}),
    "price_image_only": Plain(
        "Your price is inside a picture",
        "AI shoppers can't read text in pictures, so they don't know what your product costs and won't buy it.",
        "Type the price as normal text in your product's price box instead of putting it in an image.",
        {"shopify": "In Shopify: Products > choose the product > type the price in the Price box. Remove any picture that shows the price.",
         "wix": "In Wix: Store Products > choose the product > type the price in the Price box. Remove any picture that shows the price.",
         "woocommerce": "In WordPress: Products > Edit product > Product data > type it in Regular price. Remove any picture that shows the price."}),
    "price_missing": Plain(
        "AI shoppers can't find a price",
        "A shopping assistant won't buy something when it can't see the price.",
        "Show the price with its currency next to the product name, for example $24.00.",
        {"shopify": "In Shopify: Products > choose the product > fill in the Price box, then check your theme shows it on the product page.",
         "wix": "In Wix: Store Products > choose the product > fill in the Price box.",
         "woocommerce": "In WordPress: Products > Edit product > Product data > Regular price."}),
    "jsonld_missing": Plain(
        "Your product page is missing the details AI shoppers read first",
        "Shopping assistants rely on a hidden summary of name, price and stock to compare and buy; without it they guess or skip you.",
        "Turn on product details for search engines on your product pages, or ask your developer to add them.",
        {"shopify": "In Shopify: most themes add this automatically. If it's missing, your theme may have removed it; ask your theme developer or try a structured-data app from the Shopify App Store.",
         "wix": "In Wix: product pages include this for Wix Stores products. Check SEO > Structured data markup on the product page hasn't been removed.",
         "woocommerce": "In WordPress: WooCommerce adds this by default. If an SEO plugin such as Yoast or Rank Math is installed, check its schema settings for products."}),
    "jsonld_incomplete": Plain(
        "Some product details AI shoppers need are missing",
        "Without the full name, price, currency and stock, an assistant can't confirm it's buying the right thing.",
        "Fill in every product field: name, price, currency and stock, and ask your developer to check the hidden product summary.",
        {"shopify": "In Shopify: check the product has a price and inventory set; if details are still missing, ask your theme developer.",
         "wix": "In Wix: check the product's price and inventory are set in Store Products.",
         "woocommerce": "In WordPress: check Regular price and Stock status are set under Product data."}),
    "stock_missing": Plain(
        "AI shoppers can't tell if it's in stock",
        "Assistants avoid products they can't confirm are available, to save their shopper a wasted order.",
        "Show In stock or Out of stock on the product page.",
        {"shopify": "In Shopify: Products > choose the product > Inventory, turn on Track quantity; most themes then show availability.",
         "wix": "In Wix: Store Products > choose the product > Inventory, set the stock status.",
         "woocommerce": "In WordPress: Products > Edit product > Inventory > Stock status."}),
    "oos_still_buyable": Plain(
        "It says sold out, but people can still buy it",
        "Conflicting stock information makes assistants distrust the page, and a real sale may fail later.",
        "When something is sold out, hide or switch off its Buy button.",
        {"shopify": "In Shopify: Products > Inventory, untick Continue selling when out of stock.",
         "wix": "In Wix: Store Products > Inventory, mark it Out of stock so the button is turned off.",
         "woocommerce": "In WordPress: Products > Inventory, set Stock status to Out of stock and turn off backorders."}),
    "currency_missing": Plain(
        "Your price doesn't say which currency",
        "An assistant comparing shops can't tell 24.00 dollars from 24.00 euros, so it may skip you.",
        "Show the currency symbol with every price, for example $24.00.",
        {"shopify": "In Shopify: Settings > Store details > Store currency, and check the currency format includes the symbol.",
         "wix": "In Wix: Settings > Language & region, check the currency and format.",
         "woocommerce": "In WordPress: WooCommerce > Settings > General > Currency options."}),
    "image_alt_missing": Plain(
        "Your product photo has no description",
        "Assistants that look at images, and shoppers using screen readers, can't tell what the photo shows.",
        "Give each product photo a short description, such as the product's name.",
        {"shopify": "In Shopify: Products > choose the product > click the image > Add alt text.",
         "wix": "In Wix: Store Products > choose the image > add a description in the image settings.",
         "woocommerce": "In WordPress: Media Library > choose the image > fill in Alternative Text."}),
    "sale_claim_misleading": Plain(
        "Your sale price doesn't add up",
        "Assistants check discounts; a claim that doesn't match the real price looks misleading and costs trust.",
        "Make the 'was' price and the discount match the real current price, or remove them.",
        {"shopify": "In Shopify: Products > choose the product > set Compare-at price so the discount is correct.",
         "wix": "In Wix: Store Products > choose the product > set the Discount so the shown sale matches.",
         "woocommerce": "In WordPress: Products > Edit product > set Sale price so it matches your badge."}),
    "buy_button_nonsemantic": Plain(
        "AI shoppers can't tell which button buys",
        "When the buttons say things like Go or Continue, an assistant may click the wrong one or give up.",
        "Use one clear button that says Buy now or Add to cart.",
        {"shopify": "In Shopify: Online Store > Themes > Customize > product page, use the theme's Buy buttons block instead of custom buttons.",
         "wix": "In Wix: use the built-in Add to Cart button on the product page instead of custom buttons.",
         "woocommerce": "In WordPress: use WooCommerce's Add to cart button; check your theme or page builder hasn't replaced it."}),
    "buy_button_missing": Plain(
        "There's no Buy button",
        "No button means no purchase, for assistants and people alike.",
        "Add a clear Buy now or Add to cart button next to the price.",
        {"shopify": "In Shopify: Online Store > Themes > Customize > product page, add the Buy buttons block.",
         "wix": "In Wix: add the Add to Cart button to your product page.",
         "woocommerce": "In WordPress: check the product has a price and is set to In stock; WooCommerce then shows Add to cart."}),
    "buy_button_covered": Plain(
        "Something covers your Buy button",
        "A banner sitting on the button means the assistant's click lands on the banner, not on Buy.",
        "Move your cookie banner or pop-up so it never covers the Buy button, for example a slim bar at the bottom.",
        {"shopify": "In Shopify: check your cookie or pop-up app's position settings, or Online Store > Preferences > Customer privacy.",
         "wix": "In Wix: Settings > Cookie banner, choose a position that doesn't cover the page.",
         "woocommerce": "In WordPress: open your cookie plugin's settings and choose a bottom bar position."}),
    "extra_form_step": Plain(
        "Shoppers must fill in an extra form before paying",
        "Every extra step loses shoppers; an assistant may not know what to type and stop.",
        "Remove the form before payment, or make its questions optional.",
        {"shopify": "In Shopify: check apps that add pre-checkout forms or surveys and move them after the order.",
         "wix": "In Wix: remove the form from the cart or checkout page, or mark its fields optional.",
         "woocommerce": "In WordPress: check checkout field plugins and make extra fields optional."}),
    "checkout_not_reached": Plain(
        "AI shoppers couldn't get to checkout",
        "If the path to checkout isn't clear, the sale never happens.",
        "Make the Buy or Add to cart button go straight to the cart and a clear Checkout button.",
        {}),
    "price_changed_at_checkout": Plain(
        "The price changes at checkout",
        "A surprise price makes careful assistants stop the purchase, and shoppers feel misled.",
        "Show the same price at checkout as on the product page, and show any fee as its own line from the start.",
        {}),
    "paypal_button_missing": Plain(
        "AI shoppers couldn't find a PayPal button",
        "Shopping assistants that pay with PayPal need a PayPal button they can see at checkout.",
        "Turn on PayPal at checkout and make sure its button shows.",
        {"shopify": "In Shopify: Settings > Payments, activate PayPal.",
         "wix": "In Wix: Settings > Accept payments, connect PayPal.",
         "woocommerce": "In WordPress: install WooCommerce PayPal Payments and enable it under WooCommerce > Settings > Payments."}),
    "paypal_button_hidden": Plain(
        "Your PayPal button is hidden",
        "A button the shopper can't see can't be clicked.",
        "Make sure the PayPal button is visible on the cart or checkout page.",
        {}),
    "paypal_button_covered": Plain(
        "Something covers your PayPal button",
        "The click lands on whatever is on top, so the payment never starts.",
        "Move banners and pop-ups away from the PayPal button.",
        {}),
    "popup_not_opened": Plain(
        "Clicking PayPal didn't open PayPal",
        "If the PayPal window doesn't open, the shopper can't pay.",
        "Ask your developer to check the PayPal button setup on your checkout page.",
        {}),
    "capture_error": Plain(
        "The payment was approved but your store didn't complete it",
        "The shopper said yes and still didn't get an order, which loses the sale.",
        "Ask your developer to check how your store completes PayPal payments.",
        {}),
    "capture_unconfirmed": Plain(
        "No order confirmation after paying",
        "Without a confirmation page, shoppers and assistants can't tell the order went through.",
        "Show an order confirmation page with the order number after payment.",
        {}),
    "amount_mismatch": Plain(
        "Your store charged a different price than it showed",
        "Charging more than the shown price is the fastest way to lose a shopper's trust.",
        "Make sure the amount sent to PayPal is the same as the price on the product page.",
        {}),
    "capture_amount_mismatch": Plain(
        "The amount taken didn't match the order",
        "Shoppers notice when they're charged differently from what they agreed to.",
        "Ask your developer to check the payment amount your store asks PayPal to take.",
        {}),
    "currency_mismatch": Plain(
        "The payment used a different currency",
        "Charging in another currency surprises shoppers.",
        "Use the same currency on the product page and at payment.",
        {}),
    "order_capture_mismatch": Plain(
        "Your records don't match PayPal's",
        "Mismatched records make refunds and support harder.",
        "Ask your developer to store the payment reference PayPal sends back.",
        {}),
    "agent_gave_up": Plain("The AI shopper gave up", "It couldn't find a way forward on your store.",
                           "Start with the fixes above; they're what stopped it.", {}),
    "agent_loop": Plain("The AI shopper got stuck going round in circles", "It kept trying the same thing.",
                        "Start with the fixes above, especially unclear buttons.", {}),
    "step_limit": Plain("The AI shopper ran out of time", "The path to buying was too long.",
                        "Shorten the path from your home page to checkout.", {}),
    "step_timeouts": Plain("Your pages were too slow", "Slow pages make assistants give up.",
                           "Speed up your pages, for example by making images smaller.", {}),
    "payment_failed": Plain("The purchase didn't finish", "The steps above stopped the payment.",
                            "Start with the payment fixes above.", {}),
}

# What we tell the shopkeeper about things that aren't their fault (no fix needed).
NOT_YOUR_FAULT: dict[str, str] = {
    "site_blocked": "Your site's security check blocked our visit. That isn't a problem with your store, but some AI shoppers may be blocked too.",
    "live_store_browse_only": "We only test real payments on our own demo store, so we stopped at your PayPal button and didn't pay.",
    "capture_declined": "The test buyer's card was declined. Nothing to fix in your store.",
    "popup_blocked_by_browser": "The browser blocked the PayPal window. Nothing to fix in your store.",
    "over_budget": "The total was above the spending limit you set, so the shopper did not pay. Nothing to fix in your store.",
    "approval_timeout": "PayPal took too long to finish. Nothing to fix in your store.",
    "human_approval_timeout": "PayPal asked for a person to confirm and nobody did in time. Nothing to fix in your store.",
    "paypal_error_page": "PayPal showed an error page during the test payment. Nothing to fix in your store.",
    "approval_cancelled": "The payment was cancelled in the PayPal window.",
    "fee_inconsistent": "PayPal's fee figures didn't add up. Nothing to fix in your store.",
    "fee_missing": "PayPal didn't send fee details. Nothing to fix in your store.",
    "capture_pending": "PayPal is still holding the payment for review.",
    "blocked_by_environment": "Something outside your store stopped this part of the check.",
    "run_error": "Our check itself hit a problem. Please run it again.",
    "verification_unavailable": "We couldn't double-check the payment this time. Please run it again.",
}


def plain_fix(code: str | None, platform: str = "unknown") -> dict[str, Any] | None:
    p = PLAIN.get(code or "")
    if p is None:
        return None
    return {"title": p.title, "why": p.why, "how": p.how, "steps": p.steps.get(platform),
            "platform": platform if platform in p.steps else None}


# --- Status ---

def status_for(total: int, possible: int) -> dict[str, str]:
    """Traffic light, always with words: colour is never the only signal."""
    if not possible:
        return {"level": "unknown", "text": "We couldn't check your store this time"}
    if total >= 80:
        return {"level": "good", "text": "Ready for AI shoppers"}
    if total >= 50:
        return {"level": "warn", "text": "Some fixes needed"}
    return {"level": "bad", "text": "AI shoppers will struggle to buy"}


# --- Narration: the live step feed in plain words ---

CLICKED_RE = re.compile(r"Clicked e\d+ '([^']*)'")
NOW_ON_RE = re.compile(r"Now on: (.*?) \(https?://")

EVENTS = {
    "price_in_text": ("Read the price: {snippet}", "Couldn't read the price"),
    "structured_data": ("Found the product details AI shoppers read", "Couldn't find the product details AI shoppers read"),
    "stock_readable": ("Saw whether it's in stock", "Couldn't tell if it's in stock"),
    "clear_buy_button": ("Found the Buy button", "Couldn't tell which button buys"),
    "buy_button_unobstructed": (None, "Something covers the Buy button"),
    "currency_stated": (None, "The price doesn't say which currency"),
    "stock_consistent": (None, "It says sold out but still sells it"),
    "image_alt_text": (None, "The product photo has no description"),
    "sale_claim_consistent": (None, "The sale price doesn't add up"),
    "no_extra_steps": (None, "Had to fill in an extra form first"),
    "checkout_reached": ("Reached checkout", "Couldn't reach checkout"),
    "price_consistent": ("Checkout shows the same price", "The price changed at checkout"),
    "paypal_button_found": ("The PayPal button is ready", "Couldn't use the PayPal button"),
    "popup_opened": ("PayPal opened", None),
    "payment_approved": ("Approved the test payment", None),
    "capture_completed": ("Payment went through (sandbox test)", "The payment didn't go through"),
    "payment_verified": ("The amount and fees match", "The amounts don't match"),
}


def short_title(title: str) -> str:
    return re.split(r"\s[|–—-]\s", title or "")[0].strip() or "your product"


def narrate(steps: list[dict[str, Any]], checks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """One plain sentence per thing that happened, in order, with good/bad/neutral tone."""
    by_step: dict[int, list[dict[str, Any]]] = {}
    for c in checks:
        if c.get("step_id") is not None:
            by_step.setdefault(c["step_id"], []).append(c)
    feed: list[dict[str, Any]] = []
    for s in steps:
        obs = s.get("observation") or ""
        tool = s["tool"]
        text = None
        if not s.get("ok"):
            text = "That didn't work, trying something else" if tool != "finish" else None
        elif tool == "open_page":
            m = NOW_ON_RE.search(obs)
            text = f"Opened {short_title(m.group(1))}" if m else "Opened a page"
        elif tool == "click":
            m = CLICKED_RE.search(obs)
            text = f"Clicked “{m.group(1)}”" if m and m.group(1) else "Clicked a button"
        elif tool == "fill_form":
            text = "Filled in a form"
        elif tool == "read_text":
            text = "Read the page"
        elif tool == "find_elements":
            text = "Looked at the links and buttons"
        elif tool == "check_paypal_button":
            text = "Checked the PayPal button (no payment on live stores)"
        elif tool == "pay_with_paypal":
            text = "Paid with PayPal (sandbox test)" if obs.startswith("Payment complete") else "Tried to pay with PayPal"
        if text:
            feed.append({"step": s["idx"], "text": text, "tone": "neutral"})
        for c in by_step.get(s["id"], []):
            if c["check_key"] == "product_found" and c["passed"] == 1:
                feed.append({"step": s["idx"], "text": f"Found your {short_title((c.get('evidence') or {}).get('title') or '')}",
                             "tone": "good"})
                continue
            good, bad = EVENTS.get(c["check_key"], (None, None))
            if c["passed"] == 1 and good:
                snippet = (c.get("evidence") or {}).get("snippet") or ""
                feed.append({"step": s["idx"], "text": good.format(snippet=snippet).rstrip(": "), "tone": "good"})
            elif c["passed"] == 0 and bad:
                tone = "info" if c.get("cause") == "environment" else "bad"
                feed.append({"step": s["idx"], "text": bad, "tone": tone})
    return feed
