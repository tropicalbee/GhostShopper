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
    capture_response TEXT,
    run_id           INTEGER
);

CREATE TABLE IF NOT EXISTS runs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at      TEXT NOT NULL,
    finished_at     TEXT,
    status          TEXT NOT NULL,          -- running | awaiting_human | completed | error
    browser         TEXT NOT NULL,          -- local | kernel
    store_url       TEXT NOT NULL,
    goal            TEXT NOT NULL,
    target_product  TEXT NOT NULL,
    checkout        INTEGER NOT NULL,       -- 1 = run includes the PayPal payment
    paypal_mode     TEXT NOT NULL,          -- off | mock | sandbox
    flaws_snapshot  TEXT,                   -- JSON
    llm             TEXT NOT NULL,          -- mock | groq
    model           TEXT,
    outcome         TEXT,                   -- reached_checkout | purchased | blocked | gave_up | error (deterministic)
    end_reason      TEXT,                   -- finished | agent_gave_up | agent_loop | step_limit | step_timeouts | error
    agent_summary   TEXT,
    agent_report    TEXT,                   -- JSON: what the agent says it read and its own outcome (not scored)
    step_count      INTEGER NOT NULL DEFAULT 0,
    order_id        TEXT,
    awaiting        TEXT,                   -- JSON while status = awaiting_human: stage, reason, since, live view
    error           TEXT
);

CREATE TABLE IF NOT EXISTS steps (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id          INTEGER NOT NULL REFERENCES runs(id),
    idx             INTEGER NOT NULL,
    tool            TEXT NOT NULL,
    args            TEXT,                   -- JSON
    thought         TEXT,
    observation     TEXT,
    ok              INTEGER NOT NULL,
    url             TEXT,
    screenshot_path TEXT,
    duration_ms     INTEGER,
    created_at      TEXT NOT NULL
);

-- Every check outcome, pass or fail. The score is computed from this table only.
CREATE TABLE IF NOT EXISTS checks (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id      INTEGER NOT NULL REFERENCES runs(id),
    step_id     INTEGER REFERENCES steps(id),
    check_key   TEXT NOT NULL,
    stage       TEXT NOT NULL,
    passed      INTEGER,                    -- 1 pass, 0 fail, NULL not tested
    code        TEXT,                       -- failure type (failures.FAILURE_TYPES)
    cause       TEXT,                       -- store | environment (failed / not tested only)
    severity    TEXT NOT NULL,
    reason      TEXT NOT NULL,
    evidence    TEXT,                       -- JSON: url, selector, screenshot, snippet
    fix         TEXT,                       -- LLM explanation (Day 5), never scored
    created_at  TEXT NOT NULL,
    UNIQUE (run_id, check_key)
);

CREATE VIEW IF NOT EXISTS failures AS
    SELECT * FROM checks WHERE passed IS NOT 1;

CREATE TABLE IF NOT EXISTS scores (
    run_id        INTEGER PRIMARY KEY REFERENCES runs(id),
    total         INTEGER NOT NULL,         -- 0-100 over `possible`
    possible      INTEGER,                  -- points the store is judged on (100 minus excluded)
    discover      INTEGER NOT NULL,
    details       INTEGER NOT NULL,
    checkout      INTEGER NOT NULL,
    payment       INTEGER NOT NULL,
    outcome       INTEGER,
    breakdown     TEXT NOT NULL,            -- JSON fix list
    excluded      TEXT,                     -- JSON: checks excluded as not the store's fault
    rules_version TEXT NOT NULL,
    created_at    TEXT NOT NULL
);
"""

# Columns added after a table first shipped; CREATE TABLE IF NOT EXISTS won't add them to old databases.
ADDED_COLUMNS = {
    "orders": {"run_id": "INTEGER"},
    "runs": {"end_reason": "TEXT", "awaiting": "TEXT"},
    "checks": {"code": "TEXT", "cause": "TEXT"},
    "scores": {"possible": "INTEGER", "outcome": "INTEGER", "excluded": "TEXT"},
}


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
        existing = {}
        for table in ADDED_COLUMNS:
            existing[table] = {r["name"] for r in conn.execute(f"PRAGMA table_info({table})")}
        for table, columns in ADDED_COLUMNS.items():
            if not existing[table]:
                continue  # new table: SCHEMA creates it with every column
            for name, sql_type in columns.items():
                if name not in existing[table]:
                    conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {sql_type}")
        conn.executescript(SCHEMA)


def link_order_to_run(db_path: Path, order_id: str, run_id: int) -> bool:
    """Returns False if the order is not in this database (the run then keeps no order link)."""
    with connect(db_path) as conn:
        if conn.execute("UPDATE orders SET run_id = ? WHERE order_id = ?", (run_id, order_id)).rowcount == 0:
            return False
        conn.execute("UPDATE runs SET order_id = ? WHERE id = ?", (order_id, run_id))
        return True


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


def get_order(db_path: Path, order_id: str, include_raw: bool = False) -> dict[str, Any] | None:
    with connect(db_path) as conn:
        row = conn.execute("SELECT * FROM orders WHERE order_id = ?", (order_id,)).fetchone()
    if row is None:
        return None
    order = dict(row)
    if not include_raw:
        order.pop("capture_response", None)
    return order
