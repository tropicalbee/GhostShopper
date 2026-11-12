"""Purchase trace benchmark: does the trace (backend/app/trace.py) report the right first mismatch?

The detection benchmark (benchmark.py) measures the scored checks; the trace sits outside the score, so it is
measured here on its own. Each purchase scenario is a real mock purchase (store flaw x PayPal outcome) read back
through GET /api/runs/{id}. The link-integrity scenarios take one healthy purchase and tamper with the recorded ids
before the trace is built, then put the records back. The expected results are written by hand in trace_truth.py.
"""

import asyncio
import json
import sqlite3
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

from ..agent.loop import DEFAULT_TARGET, RunConfig, run_shopper
from ..agent.paypal_flow import make_payment_handler
from ..agent.service import apply_flaws
from ..config import REPO_ROOT, Settings
from ..trace import EXPLANATIONS, LINKS
from .navigator import ScriptedNavigator
from .server import LiveServer
from .trace_truth import CASES, PAYPAL, SKIPPED, Case

OTHER_ORDER, OTHER_CAPTURE, OTHER_NUMBER = "MOCKOTHERORDER1", "MOCKCAPOTHER0001", "9999"
LINK_KEYS = [k for k, _, _ in LINKS]


def _code(mismatch: dict[str, Any]) -> str:
    """The mismatch code, read from the fix text each code owns (the field alone cannot tell the status codes apart)."""
    if mismatch["field"] in LINK_KEYS:
        return "records_not_linked"
    return next(code for code, (_, fix) in EXPLANATIONS.items() if fix == mismatch["fix"])


def _show(first: tuple[str, str] | None) -> str:
    return f"{first[0]} @ {first[1]}" if first else "none"


def evaluate(case: Case, trace: dict[str, Any]) -> dict[str, Any]:
    first = trace["first_mismatch"]
    actual = (_code(first), first["stage"]) if first else None
    links = tuple(link["kind"] for link in trace["links"])
    first_ok, links_ok = actual == case.first, links == case.links
    return {
        "id": case.id, "category": case.category, "flaw": case.flaw, "paypal": case.paypal,
        "expected": _show(case.first), "actual": _show(actual),
        "expected_links": list(case.links or ()), "actual_links": list(links),
        "first_ok": first_ok, "links_ok": links_ok, "passed": first_ok and links_ok,
        "mismatch_count": len(trace["mismatches"]), "why": case.why,
    }


# The server shares this process (and the machine) with up to four browsers: httpx's default 5s connect timeout is
# shorter than the server thread can be starved for under load (seen as a bare ConnectTimeout in the benchmark).
HTTP_TIMEOUT_S = 30.0


async def _trace(srv: LiveServer, run_id: int) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT_S) as http:
        resp = await http.get(f"{srv.url}/api/runs/{run_id}")
        resp.raise_for_status()
    return resp.json()["trace"]


async def _purchase(srv: LiveServer, db_path: Path, runs_dir: Path, flaw: str, scenario: str) -> int:
    store_url = f"{srv.url}/store/"
    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT_S) as http:
        (await http.put(f"{srv.url}/mock-paypal/scenario", json={"scenario": scenario})).raise_for_status()
    snapshot = await apply_flaws(store_url, "off" if flaw == "healthy" else flaw)
    payment = make_payment_handler("mock", store_url, "mock", True)
    cfg = RunConfig(store_url=store_url, db_path=db_path, flaws=snapshot, checkout=True, paypal_mode="mock",
                    max_steps=45, runs_dir=runs_dir)
    return await run_shopper(cfg, ScriptedNavigator(DEFAULT_TARGET), payment)


async def run_purchase_case(srv: LiveServer, db_path: Path, runs_dir: Path, case: Case) -> dict[str, Any]:
    started = time.monotonic()
    run_id = await _purchase(srv, db_path, runs_dir, case.flaw, PAYPAL[case.paypal])
    result = evaluate(case, await _trace(srv, run_id))
    return {**result, "run_id": run_id, "seconds": round(time.monotonic() - started, 1)}


# -- link integrity: tamper with the recorded data of one healthy purchase ------------------------------------------

def _tampered(case_id: str, store: dict[str, Any], order: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """The store order row and the PayPal order row (order_response and capture_response parsed) after tampering."""
    order_response, capture_response = order["order_response"], order["capture_response"]
    unit = order_response["purchase_units"][0]
    if case_id == "link-custom_id-missing":
        unit.pop("custom_id")
    elif case_id == "link-custom_id-wrong":
        unit["custom_id"] = OTHER_NUMBER
    elif case_id == "link-store-points-to-other-order":
        # PayPal's other order is itself consistent: its own id, another store order's number, its own capture.
        order_response["id"] = capture_response["id"] = OTHER_ORDER
        unit["custom_id"] = capture_response["purchase_units"][0]["custom_id"] = OTHER_NUMBER
        for response in (order_response, capture_response):
            response["purchase_units"][0]["payments"]["captures"][0]["id"] = OTHER_CAPTURE
        store = {**store, "paypal_order_id": OTHER_ORDER}
        order = {**order, "order_id": OTHER_ORDER, "run_id": None}
    elif case_id == "link-capture-for-other-order":
        capture_response["id"] = OTHER_ORDER
    elif case_id == "link-store-capture-id-wrong":
        store = {**store, "paypal_capture_id": "MOCKCAPWRONG0001"}
    elif case_id == "link-store-capture-id-missing":
        store = {**store, "paypal_capture_id": None}
    elif case_id == "link-store-order-id-missing":
        store = {**store, "paypal_order_id": None}
    elif case_id == "link-store-order-id-missing-unpaid":
        store = {**store, "paypal_order_id": None, "status": "awaiting_payment"}
    else:
        raise KeyError(case_id)
    return store, {**order, "order_response": order_response, "capture_response": capture_response}


def _row(conn: sqlite3.Connection, sql: str, *args: Any) -> dict[str, Any]:
    return dict(conn.execute(sql, args).fetchone())


async def run_link_cases(srv: LiveServer, db_path: Path, runs_dir: Path, cases: list[Case]) -> list[dict[str, Any]]:
    """One healthy captured purchase, then each tampering in turn. The recorded rows are put back after each."""
    started = time.monotonic()
    run_id = await _purchase(srv, db_path, runs_dir, "healthy", PAYPAL["captured"])
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    store0 = _row(conn, "SELECT * FROM store_orders WHERE run_id = ? ORDER BY number DESC LIMIT 1", run_id)
    order0 = _row(conn, "SELECT * FROM orders WHERE order_id = ?", store0["paypal_order_id"])
    order0 = {**order0, "order_response": json.loads(order0["order_response"]),
              "capture_response": json.loads(order0["capture_response"])}
    results = []
    try:
        for case in cases:
            store, order = _tampered(case.id, store0, json.loads(json.dumps(order0)))
            with conn:
                if order["order_id"] != order0["order_id"]:  # another PayPal order that exists beside the real one
                    cols = [c for c in order if c not in ("order_response", "capture_response")]
                    conn.execute("INSERT OR IGNORE INTO orders (" + ",".join(cols) + ") VALUES (" + ",".join("?" * len(cols)) + ")",
                                 [order[c] for c in cols])
                conn.execute("UPDATE orders SET order_response = ?, capture_response = ? WHERE order_id = ?",
                             (json.dumps(order["order_response"]), json.dumps(order["capture_response"]), order["order_id"]))
                conn.execute("UPDATE store_orders SET paypal_order_id = ?, paypal_capture_id = ?, status = ? WHERE number = ?",
                             (store["paypal_order_id"], store["paypal_capture_id"], store["status"], store0["number"]))
            try:
                trace = await _trace(srv, run_id)
            finally:
                with conn:  # put the healthy records back
                    conn.execute("UPDATE orders SET order_response = ?, capture_response = ? WHERE order_id = ?",
                                 (json.dumps(order0["order_response"]), json.dumps(order0["capture_response"]), order0["order_id"]))
                    conn.execute("UPDATE store_orders SET paypal_order_id = ?, paypal_capture_id = ?, status = ? WHERE number = ?",
                                 (store0["paypal_order_id"], store0["paypal_capture_id"], store0["status"], store0["number"]))
            results.append({**evaluate(case, trace), "run_id": run_id, "seconds": 0.0})
    finally:
        conn.close()
    if results:
        results[0]["seconds"] = round(time.monotonic() - started, 1)  # the purchase is charged to the first case
    return results


# -- the matrix --------------------------------------------------------------------------------------------------------

async def run_trace_matrix(cases: tuple[Case, ...] = CASES, *, workers: int = 4, out_dir: Path | None = None,
                           label: str = "trace") -> dict[str, Any]:
    from ..main import create_app

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_dir = out_dir or REPO_ROOT / "data" / "eval" / f"{label}-{stamp}"
    out_dir.mkdir(parents=True, exist_ok=True)
    link_cases = [c for c in cases if c.category == "links"]
    jobs: list[Any] = [c for c in cases if c.category != "links"]
    if link_cases:
        jobs.append(link_cases)  # one job: a purchase, then every tampering
    queue: asyncio.Queue[Any] = asyncio.Queue()
    for job in jobs:
        queue.put_nowait(job)
    results: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []

    async def worker(i: int) -> None:
        db_path = out_dir / f"worker{i}.db"
        settings = Settings("", "", db_path, "http://unused", paypal_mode="mock", dev_options=True)  # local only
        with LiveServer(create_app(settings)) as srv:
            while not queue.empty():
                job = queue.get_nowait()
                try:
                    if isinstance(job, list):
                        results.extend(await run_link_cases(srv, db_path, out_dir / "runs", job))
                    else:
                        results.append(await run_purchase_case(srv, db_path, out_dir / "runs", job))
                except Exception as exc:  # recorded, never silently dropped
                    ids = [c.id for c in job] if isinstance(job, list) else [job.id]
                    where = traceback.extract_tb(exc.__traceback__)[-1]
                    errors.append({"cases": ids, "worker": i,
                                   "error": f"{type(exc).__name__}: {exc} ({where.name}:{where.lineno})"[:300]})

    started = time.monotonic()
    await asyncio.gather(*(worker(i) for i in range(max(1, min(workers, len(jobs))))))
    order = {c.id: n for n, c in enumerate(cases)}
    results.sort(key=lambda r: order[r["id"]])
    report = summarize(results, errors, cases, seconds=time.monotonic() - started)
    report["out_dir"] = str(out_dir)
    (out_dir / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


def summarize(results: list[dict[str, Any]], errors: list[dict[str, Any]], cases: tuple[Case, ...], *,
              seconds: float) -> dict[str, Any]:
    by_id = {c.id: c for c in cases}
    healthy = [r for r in results if r["category"] == "healthy"]
    controls = [r for r in results if r["category"] == "control"]
    links = [r for r in results if r["category"] == "links"]
    broken = [r for r in links if by_id[r["id"]].first is not None]
    unknown = [r for r in links if by_id[r["id"]].first is None]
    return {
        "label": "trace",
        "runs": sum(c.category != "links" for c in cases) + any(c.category == "links" for c in cases),
        "errors": errors,
        "seconds": round(seconds, 1),
        "scenarios": len(cases),
        "passed": sum(r["passed"] for r in results),
        "first_mismatch_correct": sum(r["first_ok"] for r in results),
        "healthy": {"runs": len(healthy), "false_mismatches": sum(r["mismatch_count"] > 0 for r in healthy)},
        "controls": {"runs": len(controls), "false_mismatches": sum(r["mismatch_count"] > 0 for r in controls)},
        "broken_links": {"total": len(broken), "detected": sum(r["first_ok"] for r in broken)},
        "unknown_links": {"total": len(unknown), "not_guessed": sum(r["passed"] for r in unknown)},
        "skipped": SKIPPED,
        "results": results,
    }


def _abbr(kinds: list[str]) -> str:
    return "/".join({"unknown": "unk", "broken": "brk"}.get(k, k) for k in kinds)


def markdown(report: dict[str, Any]) -> str:
    n = report["scenarios"]
    h, c, b, u = report["healthy"], report["controls"], report["broken_links"], report["unknown_links"]
    lines = [
        f"**trace**: {n} scenarios, {report['runs']} mock purchases, {report['seconds']}s total, "
        f"errors: {len(report['errors'])}.",
        "",
        "| Id | Store flaw | PayPal outcome | Expected | Actual | Links expected / actual | Result |",
        "|---|---|---|---|---|---|---|",
    ]
    for r in report["results"]:
        lines.append(f"| {r['id']} | {r['flaw']} | {r['paypal']} | {r['expected']} | {r['actual']} | "
                     f"{_abbr(r['expected_links'])} / {_abbr(r['actual_links'])} | {'pass' if r['passed'] else 'FAIL'} |")
    for e in report["errors"]:
        lines.append(f"| {', '.join(e['cases'])} | | | | ERROR: {e['error']} | | ERROR |")
    lines += [
        "",
        f"Scenarios passed: {report['passed']}/{n}.",
        f"First-mismatch accuracy: {report['first_mismatch_correct']}/{n}.",
        f"False mismatches on healthy runs: {h['false_mismatches']}/{h['runs']}.",
        f"False mismatches on flaw-switched-on runs where the flaw is not triggered: {c['false_mismatches']}/{c['runs']}.",
        f"Broken-link detection: {b['detected']}/{b['total']}.",
        f"Unknown not guessed: {u['not_guessed']}/{u['total']}.",
        "",
        "Skipped combinations: " + "; ".join(f"{k} ({v})" for k, v in report["skipped"].items()) + ".",
    ]
    failed = [r for r in report["results"] if not r["passed"]]
    if failed:
        lines += ["", "Failing scenarios:"] + [
            f"- {r['id']}: expected {r['expected']}, got {r['actual']}; links expected {_abbr(r['expected_links'])}, "
            f"got {_abbr(r['actual_links'])}. {r['why']}" for r in failed]
    return "\n".join(lines)
