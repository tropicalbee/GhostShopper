"""SQLite storage for sandbox checkout orders."""

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterator

from store.orders import ensure_schema as ensure_store_orders

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
    order_response   TEXT,                  -- PayPal's GET order response, read after payment
    capture_error    TEXT,                  -- PayPal's issue when the capture failed (e.g. INSTRUMENT_DECLINED)
    run_id           INTEGER,
    refund_id        TEXT,
    refund_status    TEXT,
    refund_amount    TEXT,
    refund_currency  TEXT,
    refunded_at      TEXT
);

CREATE TABLE IF NOT EXISTS vault_tokens (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    paypal_mode      TEXT NOT NULL,
    payment_token_id TEXT NOT NULL,
    customer_id      TEXT,
    created_at       TEXT NOT NULL
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
    llm             TEXT NOT NULL,          -- mock | live | scripted
    model           TEXT,
    outcome         TEXT,                   -- reached_checkout | purchased | blocked | gave_up | error (deterministic)
    end_reason      TEXT,                   -- finished | agent_gave_up | agent_loop | step_limit | step_timeouts | error
    agent_summary   TEXT,
    agent_report    TEXT,                   -- JSON: what the agent says it read and its own outcome (not scored)
    step_count      INTEGER NOT NULL DEFAULT 0,
    order_id        TEXT,
    awaiting        TEXT,                   -- JSON while status = awaiting_human: stage, reason, since, live view
    live            INTEGER NOT NULL DEFAULT 0,  -- 1 = a real store: browse-only, never pays
    platform        TEXT,                   -- shopify | wix | woocommerce | unknown
    platform_evidence TEXT,                 -- JSON list of the signals that decided it
    paypal_readiness TEXT,                  -- JSON: PayPal setup checklist, recommendations and 0-100 figure
    budget          TEXT,                   -- spending limit in USD ("30.00"), NULL = none
    product_snapshot TEXT,                  -- JSON: what the shopper read on the product page (feeds the product feed)
    agent_safety    TEXT,                   -- JSON: text aimed at AI agents the shopper met (agent/injection.py). Not scored.
    error           TEXT,
    owner_hash      TEXT                    -- SHA-256 of the browser's owner token; NULL = shared example
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

# Idempotent. runs(owner_hash, store_url, id) serves the per-browser list and before/after lookups,
# runs(started_at) the retention purge, steps(run_id, idx) the ordered step load, orders(run_id) the unlink on delete.
INDEXES = """
CREATE INDEX IF NOT EXISTS idx_runs_owner_store_id ON runs (owner_hash, store_url, id);
CREATE INDEX IF NOT EXISTS idx_runs_started_at ON runs (started_at);
CREATE INDEX IF NOT EXISTS idx_steps_run_idx ON steps (run_id, idx);
CREATE INDEX IF NOT EXISTS idx_orders_run ON orders (run_id);
"""

BUSY_TIMEOUT_MS = 5000  # wait this long for a competing writer instead of failing with "database is locked"

UNCLAIMED = "unclaimed"  # owner_hash of runs made before checks belonged to a browser; no token hashes to it

# Columns added after a table first shipped; CREATE TABLE IF NOT EXISTS won't add them to old databases.
ADDED_COLUMNS = {
    "orders": {"run_id": "INTEGER", "refund_id": "TEXT", "refund_status": "TEXT", "refund_amount": "TEXT",
               "refund_currency": "TEXT", "refunded_at": "TEXT", "order_response": "TEXT", "capture_error": "TEXT"},
    "runs": {"end_reason": "TEXT", "awaiting": "TEXT", "live": "INTEGER NOT NULL DEFAULT 0", "platform": "TEXT",
             "platform_evidence": "TEXT", "owner_hash": "TEXT", "paypal_readiness": "TEXT", "budget": "TEXT",
             "product_snapshot": "TEXT", "agent_safety": "TEXT"},
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
    conn.execute(f"PRAGMA busy_timeout={BUSY_TIMEOUT_MS}")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db(db_path: Path) -> None:
    with connect(db_path) as conn:
        # WAL lets the dashboard's reads proceed while a run writes. Persistent in the file, so once is enough;
        # synchronous=NORMAL is the safe pairing for WAL (a power cut can lose the last commit, never corrupt).
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        existing = {}
        for table in ADDED_COLUMNS:
            existing[table] = {r["name"] for r in conn.execute(f"PRAGMA table_info({table})")}
        for table, columns in ADDED_COLUMNS.items():
            if not existing[table]:
                continue  # new table: SCHEMA creates it with every column
            for name, sql_type in columns.items():
                if name not in existing[table]:
                    conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {sql_type}")
                    if (table, name) == ("runs", "owner_hash"):
                        # Runs from before ownership existed belong to nobody we can identify. NULL would make
                        # them shared examples, so they become unclaimed: hidden from the web, kept for the CLI.
                        conn.execute("UPDATE runs SET owner_hash = ?", (UNCLAIMED,))
        conn.executescript(SCHEMA)
        ensure_store_orders(conn)
        conn.executescript(INDEXES)


def save_vault_token(db_path: Path, *, paypal_mode: str, payment_token_id: str, customer_id: str | None) -> None:
    """Keep the buyer's PayPal payment token (a secret-ish id: never shown to the LLM, redacted in run logs)."""
    with connect(db_path) as conn:
        conn.execute("INSERT INTO vault_tokens (paypal_mode, payment_token_id, customer_id, created_at)"
                     " VALUES (?, ?, ?, ?)", (paypal_mode, payment_token_id, customer_id, _now()))


def latest_vault_token(db_path: Path, paypal_mode: str) -> dict[str, Any] | None:
    """The newest token saved for this PayPal mode, or None. The table may not exist in a database never initialised."""
    with connect(db_path) as conn:
        try:
            row = conn.execute("SELECT * FROM vault_tokens WHERE paypal_mode = ? ORDER BY id DESC LIMIT 1",
                               (paypal_mode,)).fetchone()
        except sqlite3.OperationalError:
            return None
    return dict(row) if row else None


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
            " paypal_fee = ?, net_amount = ?, captured_at = ?, capture_response = ?, capture_error = NULL WHERE order_id = ?",
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


def record_capture_failure(db_path: Path, order_id: str, issue: str) -> None:
    """Keep what PayPal said when the capture failed, so the purchase trace can show it."""
    with connect(db_path) as conn:
        conn.execute("UPDATE orders SET capture_error = ? WHERE order_id = ?", (issue, order_id))


def record_order_snapshot(db_path: Path, order_id: str, raw: dict[str, Any]) -> None:
    """Keep PayPal's GET order response, read after payment."""
    with connect(db_path) as conn:
        conn.execute("UPDATE orders SET order_response = ? WHERE order_id = ?", (json.dumps(raw), order_id))


def record_refund(db_path: Path, order_id: str, refund: dict[str, Any]) -> None:
    """Store a refund once. A different refund id never overwrites one already stored; the same id may fill in details."""
    amount = refund.get("amount") or {}  # a partial (just-issued) refund may not carry these yet
    with connect(db_path) as conn:
        conn.execute(
            "UPDATE orders SET refund_id = ?, refund_status = ?, refund_amount = ?, refund_currency = ?,"
            " refunded_at = ? WHERE order_id = ? AND (refund_id IS NULL OR refund_id = ?)",
            (refund["id"], refund.get("status"), amount.get("value"), amount.get("currency_code"),
             _now(), order_id, refund["id"]),
        )


def get_order(db_path: Path, order_id: str, include_raw: bool = False) -> dict[str, Any] | None:
    with connect(db_path) as conn:
        row = conn.execute("SELECT * FROM orders WHERE order_id = ?", (order_id,)).fetchone()
    if row is None:
        return None
    order = dict(row)
    if not include_raw:
        order.pop("capture_response", None)
        order.pop("order_response", None)
    return order


def delete_run(db_path: Path, run_id: int, runs_dir: Path) -> None:
    """Remove a run, its steps, checks, score, judge ratings and screenshot folder.

    A sandbox order the run placed stays (it is the demo store's record) but loses its link to the run.
    """
    with connect(db_path) as conn:
        conn.execute("UPDATE orders SET run_id = NULL WHERE run_id = ?", (run_id,))
        conn.execute("UPDATE store_orders SET run_id = NULL WHERE run_id = ?", (run_id,))
        for table in ("steps", "checks", "scores"):
            conn.execute(f"DELETE FROM {table} WHERE run_id = ?", (run_id,))
        if conn.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'judge_ratings'").fetchone():
            conn.execute("DELETE FROM judge_ratings WHERE run_id = ?", (run_id,))
        conn.execute("DELETE FROM runs WHERE id = ?", (run_id,))
    from .agent.recorder import invalidate_run  # late import: recorder imports this module

    invalidate_run(db_path, run_id)
    _remove_run_folder(runs_dir, run_id)


def _remove_run_folder(runs_dir: Path, run_id: int) -> None:
    root = runs_dir.resolve()
    folder = runs_dir / f"run-{int(run_id)}"
    # Only a real folder named run-<id> directly under the configured runs folder, never a link out of it.
    if folder.is_symlink() or not folder.is_dir() or folder.resolve().parent != root:
        return
    for item in folder.iterdir():
        if item.is_file() and not item.is_symlink() and item.suffix == ".png":
            item.unlink()
    if not any(folder.iterdir()):
        folder.rmdir()


def purge_old_runs(db_path: Path, runs_dir: Path, days: int) -> list[int]:
    """Delete finished checks older than `days` that belong to a browser. Shared examples and unclaimed runs
    from before ownership existed are kept."""
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat(timespec="seconds")
    with connect(db_path) as conn:
        ids = [r[0] for r in conn.execute(
            "SELECT id FROM runs WHERE owner_hash IS NOT NULL AND owner_hash != ? AND started_at < ?"
            " AND status NOT IN ('running', 'awaiting_human') ORDER BY id", (UNCLAIMED, cutoff))]
    for run_id in ids:
        delete_run(db_path, run_id, runs_dir)
    return ids
