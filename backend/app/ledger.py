"""Agent sales ledger: one row per checkout attempt, with the money checked against PayPal reporting data.

Rows come from SQLite: every captured order ("agent" when a run bought it, "human" otherwise) and every
checkout run that captured nothing (a lost sale). The PayPal columns come from Transaction Search
(`PayPalClient.search_transactions`), matched on the capture id. Matching is plain arithmetic, never an LLM.
PayPal being slow or unreachable never blocks the page: the rows come back "not_checked" with `paypal_error`.
"""

import json
import logging
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import Any

import httpx
from fastapi import APIRouter, Request

from . import db
from .paypal import SEARCH_MAX_DAYS, PayPalError
from .ratelimit import rate_limit
from .runs import presenter_unlocked
from .scoring import STAGES

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["ledger"])

ENVIRONMENT = "environment"  # a check's cause when the failure was outside the store


def _dec(value: Any) -> Decimal | None:
    try:
        return Decimal(str(value)) if value not in (None, "") else None
    except InvalidOperation:
        return None


def _money(value: Decimal) -> str:
    return f"{value:.2f}"


def _failed_stages(checks: list[dict[str, Any]]) -> list[str]:
    """Stages of failed checks the store is responsible for, in path order."""
    failed = {c["stage"] for c in checks if c["passed"] == 0 and c["cause"] != ENVIRONMENT}
    return [s for s in STAGES if s in failed]


def _stopped_at(checks: list[dict[str, Any]]) -> str | None:
    store_side = _failed_stages(checks)
    if store_side:
        return store_side[0]
    any_failed = [s for s in STAGES if any(c["stage"] == s and c["passed"] == 0 for c in checks)]
    return any_failed[0] if any_failed else None


def _flaws_on(snapshot: str | None) -> list[str] | None:
    """Which flaws were on, from the run's own snapshot. None = unknown (a purchase with no run)."""
    if not snapshot:
        return None
    try:
        data = json.loads(snapshot)
    except ValueError:
        return None
    return sorted(k for k, v in data.items() if v) if isinstance(data, dict) else None


def build_rows(db_path, viewer: str, presenter: bool = False) -> list[dict[str, Any]]:
    from .agent.recorder import catalog_price_of

    # An order with no run (its run was deleted or purged) belongs to nobody, so only the presenter sees it.
    visible = ("(r.id IS NULL OR r.owner_hash IS NULL OR r.owner_hash = ?)" if presenter
               else "(r.id IS NOT NULL AND (r.owner_hash IS NULL OR r.owner_hash = ?))")
    with db.connect(db_path) as conn:
        orders = conn.execute(
            "SELECT o.*, r.flaws_snapshot AS flaws_snapshot, r.paypal_mode AS run_mode FROM orders o"
            f" LEFT JOIN runs r ON r.id = o.run_id WHERE o.capture_id IS NOT NULL AND {visible}", (viewer,)).fetchall()
        lost = conn.execute(
            "SELECT r.* FROM runs r WHERE r.checkout = 1 AND r.status IN ('completed', 'error') AND "
            "(r.owner_hash IS NULL OR r.owner_hash = ?) AND NOT EXISTS "
            "(SELECT 1 FROM orders o WHERE o.run_id = r.id AND o.capture_id IS NOT NULL)", (viewer,)).fetchall()
        checks: dict[int, list[dict[str, Any]]] = {}
        for c in conn.execute("SELECT run_id, stage, passed, cause FROM checks"):
            checks.setdefault(c["run_id"], []).append(dict(c))

    rows: list[dict[str, Any]] = []
    for o in orders:
        run_checks = checks.get(o["run_id"], []) if o["run_id"] is not None else []
        refunded = bool(o["refund_id"]) and o["refund_status"] == "COMPLETED"
        at_risk = not refunded and bool(_failed_stages(run_checks))
        mode = o["run_mode"] or ("mock" if o["order_id"].startswith("MOCK") else "sandbox")
        rows.append({
            "time": o["captured_at"] or o["created_at"],
            "source": "agent" if o["run_id"] is not None else "human",
            "run_id": o["run_id"], "store_state": _flaws_on(o["flaws_snapshot"]),
            "outcome": "refunded" if refunded else "at_risk" if at_risk else "captured",
            "stopped_at": None, "amount_at_stake": None,
            "order_id": o["order_id"], "capture_id": o["capture_id"],
            "gross": o["gross_amount"], "fee": o["paypal_fee"], "net": o["net_amount"],
            "refund": o["refund_amount"] if o["refund_id"] else None, "currency": o["currency"],
            "paypal_mode": mode, "paypal_reported": "not_checked", "paypal_status": None,
        })
    for r in lost:
        price = catalog_price_of(dict(r))
        rows.append({
            "time": r["finished_at"] or r["started_at"], "source": "agent", "run_id": r["id"],
            "store_state": _flaws_on(r["flaws_snapshot"]), "outcome": "lost",
            "stopped_at": _stopped_at(checks.get(r["id"], [])),
            "amount_at_stake": price["amount"] if price else None,
            "order_id": r["order_id"], "capture_id": None, "gross": None, "fee": None, "net": None,
            "refund": None, "currency": price["currency"] if price else None,
            "paypal_mode": r["paypal_mode"], "paypal_reported": "not_checked", "paypal_status": None,
        })
    rows.sort(key=lambda row: row["time"] or "", reverse=True)
    return rows


def reconcile(row: dict[str, Any], tx: dict[str, Any] | None) -> tuple[str, str | None]:
    """(paypal_reported, transaction status) for one captured row against the transaction PayPal reports for
    its capture id. Absent or still pending = pending. A different amount, fee or currency, or a denied
    transaction = mismatch."""
    if tx is None:
        return "pending", None
    info = tx.get("transaction_info") or {}
    status = info.get("transaction_status")
    if status == "P":
        return "pending", status
    amount = info.get("transaction_amount") or {}
    fee = info.get("fee_amount") or {}  # PayPal reports fees as negative numbers
    same = (_dec(row["gross"]) == _dec(amount.get("value"))
            and abs(_dec(row["fee"]) or Decimal(0)) == abs(_dec(fee.get("value")) or Decimal(0))
            and (not amount.get("currency_code") or amount["currency_code"] == row["currency"]))
    # A fully refunded capture may read V (reversed); that is expected for a refunded row only.
    ok_status = status == "S" or (status == "V" and row["outcome"] == "refunded")
    return ("matched" if same and ok_status else "mismatch"), status


def _parse(value: str | None) -> datetime | None:
    try:
        moment = datetime.fromisoformat(value) if value else None
    except ValueError:
        return None
    return moment if moment is None or moment.tzinfo else moment.replace(tzinfo=timezone.utc)


async def check_against_paypal(request: Request, rows: list[dict[str, Any]]) -> tuple[str | None, dict[str, str] | None]:
    """Fill paypal_reported and paypal_status on the captured rows. Returns (paypal_error, search window)."""
    state = request.app.state
    captured = [r for r in rows if r["capture_id"]]
    if not captured:
        return None, None
    now = datetime.now(timezone.utc)
    start = now - timedelta(days=SEARCH_MAX_DAYS)
    window = {"start": start.isoformat(), "end": now.isoformat()}
    errors: list[str] = []
    for mode in sorted({r["paypal_mode"] for r in captured}):
        client = state.paypal_clients.get(mode)
        if client is None:
            errors.append(f"No {mode} PayPal client is configured, so {mode} rows were not checked.")
            continue
        # PayPal's search window is 31 days; older captures stay not_checked.
        recent = [r for r in captured if r["paypal_mode"] == mode and (_parse(r["time"]) or now) >= start]
        if not recent:
            continue
        if mode == "mock":
            client.sync_from_orders(recent)  # practice mode: stored mock captures count as reported
        try:
            found = await client.search_transactions(start, now)
        except PayPalError as exc:
            log.warning("transaction search failed: %s (debug_id=%s)", exc.name, exc.debug_id)
            errors.append(f"PayPal Transaction Search failed: {exc}" + (f" (debug id {exc.debug_id})" if exc.debug_id else ""))
            continue
        except httpx.HTTPError as exc:
            log.warning("transaction search unreachable: %s", type(exc).__name__)
            errors.append("Could not reach PayPal Transaction Search.")
            continue
        by_id = {(t.get("transaction_info") or {}).get("transaction_id"): t for t in found}
        for r in recent:
            r["paypal_reported"], r["paypal_status"] = reconcile(r, by_id.get(r["capture_id"]))
    return (" ".join(errors) or None), window


def totals(rows: list[dict[str, Any]]) -> dict[str, str]:
    """Single-currency sums: the demo store sells in USD only."""
    zero = Decimal(0)
    sold = [r for r in rows if r["capture_id"]]
    return {
        "lost": _money(sum((_dec(r["amount_at_stake"]) or zero for r in rows if r["outcome"] == "lost"), zero)),
        "captured_gross": _money(sum((_dec(r["gross"]) or zero for r in sold), zero)),
        "fees": _money(sum((abs(_dec(r["fee"]) or zero) for r in sold), zero)),
        "net": _money(sum((_dec(r["net"]) or zero for r in sold), zero)),
        "refunded": _money(sum((_dec(r["refund"]) or zero for r in sold), zero)),
        "currency": "USD",
    }


@router.get("/ledger")
async def get_ledger(request: Request):
    """One row per captured order and per checkout run that captured nothing, newest first, checked against
    PayPal Transaction Search. Orders whose run is gone are shown to the presenter only."""
    rate_limit(request, "api_limiter")  # a call can cost PayPal requests
    rows = build_rows(request.app.state.settings.database_path, request.state.owner, presenter_unlocked(request))
    paypal_error, window = await check_against_paypal(request, rows)
    return {"rows": rows, "totals": totals(rows), "paypal_error": paypal_error, "paypal_window": window}
