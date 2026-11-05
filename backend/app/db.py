"""SQLite storage for sandbox checkout orders."""

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

SCHEMA = """
CREATE TABLE IF NOT EXISTS orders (
    order_id         TEXT PRIMARY KEY,
    sku              TEXT NOT NULL,
    quantity         INTEGER NOT NULL,
    currency         TEXT NOT NULL,
    amount           TEXT NOT NULL,
    status           TEXT NOT NULL,
    created_at       TEXT NOT NULL,
    capture_id       TEXT,
    capture_status   TEXT,
    gross_amount     TEXT,
    paypal_fee       TEXT,
    net_amount       TEXT,
    captured_at      TEXT,
    capture_response TEXT
);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@contextmanager
def connect(db_path: Path) -> Iterator[sqlite3.Connection]:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db(db_path: Path) -> None:
    with connect(db_path) as conn:
        conn.executescript(SCHEMA)


def insert_order(
    db_path: Path, *, order_id: str, sku: str, quantity: int, currency: str, amount: str, status: str
) -> None:
    with connect(db_path) as conn:
        conn.execute(
            "INSERT INTO orders (order_id, sku, quantity, currency, amount, status, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?)",
            (order_id, sku, quantity, currency, amount, status, _now()),
        )


def record_capture(db_path: Path, order_id: str, capture: dict[str, Any], raw: dict[str, Any]) -> None:
    with connect(db_path) as conn:
        conn.execute(
            "UPDATE orders SET status = ?, capture_id = ?, capture_status = ?, gross_amount = ?,"
            " paypal_fee = ?, net_amount = ?, captured_at = ?, capture_response = ? WHERE order_id = ?",
            (
                capture["order_status"],
                capture["capture_id"],
                capture["capture_status"],
                capture["gross_amount"],
                capture["paypal_fee"],
                capture["net_amount"],
                _now(),
                json.dumps(raw),
                order_id,
            ),
        )


def get_order(db_path: Path, order_id: str) -> dict[str, Any] | None:
    with connect(db_path) as conn:
        row = conn.execute("SELECT * FROM orders WHERE order_id = ?", (order_id,)).fetchone()
    if row is None:
        return None
    order = dict(row)
    order.pop("capture_response", None)
    return order
