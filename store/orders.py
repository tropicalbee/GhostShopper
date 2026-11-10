"""The demo store's own order records, kept apart from PayPal's.

Both payment paths create and settle orders through StoreOrders: the browser checkout (the PayPal button) and the
agent's saved-PayPal payment. The four purchase flaws (store/flaws.py) change what the store writes here, which is
what the purchase trace compares with PayPal's records.
"""

import re
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

FIRST_NUMBER = 1042

STATUS_LABELS = {
    "awaiting_payment": "Awaiting payment",
    "paid": "Paid",
    "payment_failed": "Payment failed",
    "cancelled": "Cancelled",
    "confirmed": "Confirmed",  # only the success_after_cancel flaw sets it
}
_STATUS_BY_LABEL = {label.lower(): key for key, label in STATUS_LABELS.items()}
_STATUS_LINE = re.compile(r"Status:[ \t]*([^\n]+)", re.I)

SCHEMA = """
CREATE TABLE IF NOT EXISTS store_orders (
    number          INTEGER PRIMARY KEY,
    sku             TEXT NOT NULL,
    quantity        INTEGER NOT NULL,
    amount          TEXT NOT NULL,
    currency        TEXT NOT NULL,
    status          TEXT NOT NULL,
    paypal_order_id TEXT,
    run_id          INTEGER,
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_store_orders_paypal ON store_orders (paypal_order_id);
CREATE INDEX IF NOT EXISTS idx_store_orders_run ON store_orders (run_id);
"""


def status_from_text(text: str) -> str | None:
    """The order status key named by a 'Status: Paid' line in page text, or None when there is no known status."""
    for match in _STATUS_LINE.finditer(text):
        key = _STATUS_BY_LABEL.get(match.group(1).strip().rstrip(".").lower())
        if key:
            return key
    return None


def settled_status(outcome: str, flaws: dict[str, bool]) -> str:
    """The status the store gives an order once PayPal answered: captured, declined or cancelled."""
    return {
        "captured": "awaiting_payment" if flaws["never_marks_paid"] else "paid",
        "declined": "paid" if flaws["declined_marked_paid"] else "payment_failed",
        "cancelled": "confirmed" if flaws["success_after_cancel"] else "cancelled",
    }[outcome]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class StoreOrders:
    def __init__(self, db_path: Path):
        self._db_path = db_path
        db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.executescript(SCHEMA)

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA busy_timeout=5000")  # wait for a run writing to the same file
        try:
            with conn:  # commits on success, rolls back on error
                yield conn
        finally:
            conn.close()

    def open(self, *, sku: str, quantity: int, amount: str, currency: str, retry_of: int | None,
             flaws: dict[str, bool]) -> dict[str, Any]:
        """The order for a payment attempt. A retry of a still-pending order reuses it, unless the
        duplicate_on_retry flaw is on: then every attempt makes a new order."""
        with self._connect() as conn:
            if retry_of is not None and not flaws["duplicate_on_retry"]:
                pending = conn.execute("SELECT * FROM store_orders WHERE number = ? AND sku = ? AND status = ?",
                                       (retry_of, sku, "awaiting_payment")).fetchone()
                if pending is not None:
                    return dict(pending)
            now = _now()
            cur = conn.execute(
                "INSERT INTO store_orders (number, sku, quantity, amount, currency, status, created_at, updated_at)"
                " SELECT COALESCE(MAX(number), ?) + 1, ?, ?, ?, ?, ?, ?, ? FROM store_orders",
                (FIRST_NUMBER - 1, sku, quantity, amount, currency, "awaiting_payment", now, now))
            return dict(conn.execute("SELECT * FROM store_orders WHERE rowid = ?", (cur.lastrowid,)).fetchone())

    def attach_paypal(self, number: int, paypal_order_id: str) -> None:
        with self._connect() as conn:
            conn.execute("UPDATE store_orders SET paypal_order_id = ?, updated_at = ? WHERE number = ?",
                         (paypal_order_id, _now(), number))

    def settle(self, number: int, outcome: str, flaws: dict[str, bool]) -> dict[str, Any]:
        with self._connect() as conn:
            conn.execute("UPDATE store_orders SET status = ?, updated_at = ? WHERE number = ?",
                         (settled_status(outcome, flaws), _now(), number))
            return dict(conn.execute("SELECT * FROM store_orders WHERE number = ?", (number,)).fetchone())

    def get(self, number: int) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM store_orders WHERE number = ?", (number,)).fetchone()
        return dict(row) if row else None

    def for_paypal_order(self, paypal_order_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM store_orders WHERE paypal_order_id = ? ORDER BY number DESC LIMIT 1",
                               (paypal_order_id,)).fetchone()
        return dict(row) if row else None

    def link_run(self, numbers: list[int], run_id: int) -> None:
        """Record which run made these orders, so the run's purchase trace can find them."""
        with self._connect() as conn:
            conn.executemany("UPDATE store_orders SET run_id = ? WHERE number = ?", [(run_id, n) for n in numbers])

    def for_run(self, run_id: int) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM store_orders WHERE run_id = ? ORDER BY number", (run_id,)).fetchall()
        return [dict(r) for r in rows]
