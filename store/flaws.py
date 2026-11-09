"""Deliberate agent-readiness flaws, each behind a toggle persisted in SQLite.

The classic flaws (the four agent-readiness ones plus the four PayPal-setup ones) default to ON so a fresh
store is the "bad store" in the demo; the newer ones (used by the saboteur benchmark) default to OFF. Every flaw has a ground-truth label in
backend/app/eval/ground_truth.py.
"""

import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator


@dataclass(frozen=True)
class Flaw:
    key: str
    label: str
    description: str


FLAWS: tuple[Flaw, ...] = (
    Flaw(
        "price_as_image",
        "Price only in an image",
        "Prices are drawn into an image with no text or alt attribute.",
    ),
    Flaw(
        "no_structured_data",
        "Missing structured product data",
        "No schema.org Product JSON-LD, no meta description, no SKU or availability in the page.",
    ),
    Flaw(
        "ambiguous_buttons",
        "Ambiguous buy buttons",
        "Several unlabeled div 'buttons' (Go, Continue, Proceed, an arrow); only one starts checkout.",
    ),
    Flaw(
        "extra_checkout_step",
        "Extra checkout step",
        "A required 'Your details' form sits between the product page and payment.",
    ),
    Flaw(
        "price_mismatch",
        "Price changes at checkout",
        "Checkout shows and charges $3.00 more per item than the product page.",
    ),
    Flaw(
        "oos_buyable",
        "Sold-out item still buyable",
        "Product pages say 'Sold out' (and OutOfStock in JSON-LD) but keep the buy button working.",
    ),
    Flaw(
        "image_alt_missing",
        "Broken image alt text",
        "Product photos use a camera file name (IMG_0412.JPG) as alt text.",
    ),
    Flaw(
        "cookie_banner",
        "Cookie banner over the buy button",
        "A cookie consent box sits on top of the buy controls until it is accepted.",
    ),
    Flaw(
        "currency_missing",
        "Currency missing",
        "Prices show as '24.00' with no currency, and JSON-LD has no priceCurrency.",
    ),
    Flaw(
        "misleading_sale",
        "Misleading sale price",
        "A struck-through 'was' price and a '50% off' badge that don't match the real discount.",
    ),
    Flaw(
        "no_paypal_express",
        "No PayPal on the product page",
        "The PayPal button only appears at checkout, not on the product page.",
    ),
    Flaw(
        "no_pay_later",
        "No Pay Later",
        "No Pay Later messaging next to the price and no Pay Later button at checkout.",
    ),
    Flaw(
        "no_venmo",
        "No Venmo",
        "Checkout offers no Venmo button.",
    ),
    Flaw(
        "no_card_checkout",
        "No card or guest checkout",
        "Checkout offers PayPal only, with no way to pay by card without a PayPal account.",
    ),
    Flaw(
        "no_guest_checkout",
        "Guest checkout disabled",
        "Checkout asks the shopper to create an account with a password before the PayPal button appears.",
    ),
)
FLAW_KEYS = tuple(f.key for f in FLAWS)
# Flaws in the PayPal readiness score only (they do not change any agent-readiness check).
PAYPAL_FLAWS = ("no_paypal_express", "no_pay_later", "no_venmo", "no_card_checkout")
# The four original agent-readiness flaws: the fixed benchmark matrix is built from these.
AGENT_FLAWS = ("price_as_image", "no_structured_data", "ambiguous_buttons", "extra_checkout_step")
# The demo "bad store" ("--flaws on"). New flaws stay off unless asked for.
CLASSIC_FLAWS = AGENT_FLAWS + PAYPAL_FLAWS

SCHEMA = "CREATE TABLE IF NOT EXISTS store_flaws (key TEXT PRIMARY KEY, enabled INTEGER NOT NULL)"


class FlawStore:
    def __init__(self, db_path: Path):
        self._db_path = db_path
        db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.execute(SCHEMA)
            conn.executemany(
                "INSERT OR IGNORE INTO store_flaws (key, enabled) VALUES (?, ?)",
                [(k, int(k in CLASSIC_FLAWS)) for k in FLAW_KEYS],
            )

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self._db_path)
        conn.execute("PRAGMA busy_timeout=5000")  # wait for a run writing to the same file
        try:
            with conn:  # commits on success, rolls back on error
                yield conn
        finally:
            conn.close()

    def get_all(self) -> dict[str, bool]:
        with self._connect() as conn:
            rows = conn.execute("SELECT key, enabled FROM store_flaws").fetchall()
        state = {k: k in CLASSIC_FLAWS for k in FLAW_KEYS}
        state.update({k: bool(v) for k, v in rows if k in state})
        return state

    def set_many(self, updates: dict[str, bool]) -> dict[str, bool]:
        unknown = set(updates) - set(FLAW_KEYS)
        if unknown:
            raise KeyError(", ".join(sorted(unknown)))
        with self._connect() as conn:
            conn.executemany(
                "UPDATE store_flaws SET enabled = ? WHERE key = ?",
                [(int(v), k) for k, v in updates.items()],
            )
        return self.get_all()
