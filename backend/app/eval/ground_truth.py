"""Ground truth for the flaw injector: which checks each flaw must trigger, given the other flaws present.

A flaw only counts in evaluation once it is (1) a store toggle in store/flaws.py and (2) labelled here.
Some flaws hide others (a price drawn as an image can't be compared with checkout); such checks are
"masked": excluded from precision/recall instead of being counted as misses.
"""

from dataclasses import dataclass, field

# Checks that exist to detect store flaws (precision/recall are computed over these only). Goal/outcome
# checks like checkout_reached or task_completed are reported separately as collateral.
DETECTOR_CHECKS = (
    "price_in_text", "currency_stated", "structured_data", "stock_readable", "stock_consistent",
    "image_alt_text", "sale_claim_consistent", "clear_buy_button", "buy_button_unobstructed",
    "no_extra_steps", "price_consistent", "payment_verified",
)

# Primary labels: what each flaw triggers on its own. expected() applies the interactions.
LABELS: dict[str, tuple[str, ...]] = {
    "price_as_image": ("price_in_text",),
    "no_structured_data": ("structured_data", "stock_readable"),
    "ambiguous_buttons": ("clear_buy_button",),
    "extra_checkout_step": ("no_extra_steps",),
    "price_mismatch": ("price_consistent", "payment_verified"),
    "oos_buyable": ("stock_consistent",),
    "image_alt_missing": ("image_alt_text",),
    "cookie_banner": ("buy_button_unobstructed",),
    "currency_missing": ("currency_stated", "structured_data"),
    "misleading_sale": ("sale_claim_consistent",),
}


@dataclass
class Truth:
    expected: dict[str, set[str]] = field(default_factory=dict)  # flaw -> checks it must fail
    masked: dict[str, set[str]] = field(default_factory=dict)  # flaw -> checks it would fail but can't be seen

    @property
    def all_expected(self) -> set[str]:
        return set().union(*self.expected.values()) if self.expected else set()

    @property
    def all_masked(self) -> set[str]:
        return set().union(*self.masked.values()) - self.all_expected if self.masked else set()


def expected(flaws: set[str], checkout: bool) -> Truth:
    unknown = flaws - set(LABELS)
    if unknown:
        raise ValueError(f"Flaws without ground truth: {', '.join(sorted(unknown))}")
    text_price = "price_as_image" not in flaws  # product + checkout prices readable as text
    jsonld = "no_structured_data" not in flaws
    t = Truth()

    def add(flaw: str, check: str, visible: bool = True) -> None:
        (t.expected if visible else t.masked).setdefault(flaw, set()).add(check)

    for flaw in flaws:
        if flaw == "no_structured_data":
            add(flaw, "structured_data")
            add(flaw, "stock_readable", visible="oos_buyable" not in flaws)  # "Sold out" text still states stock
        elif flaw == "price_mismatch":
            add(flaw, "price_consistent", visible=text_price)
            if checkout:
                add(flaw, "payment_verified")
        elif flaw == "currency_missing":
            add(flaw, "currency_stated", visible=text_price or jsonld)
            if jsonld:
                add(flaw, "structured_data")  # offers.priceCurrency removed
        elif flaw == "misleading_sale":
            add(flaw, "sale_claim_consistent", visible=text_price or jsonld)  # needs the current price somewhere
        else:
            for check in LABELS[flaw]:
                add(flaw, check)
    return t
