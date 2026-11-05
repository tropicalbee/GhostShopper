"""Before/after comparison of two runs: score change, failures fixed, failures remaining.

    python -m backend.app.agent.compare 4 5
    python -m backend.app.agent.compare --last      # the two most recent finished runs
"""

import sys
from pathlib import Path
from typing import Any

from .. import db
from ..scoring import CHECKS
from .recorder import list_runs, load_run


class CompareError(LookupError):
    pass


def previous_run(db_path: Path, run_id: int) -> int | None:
    """The latest earlier finished, scored check of the same store by the same browser (or, for a shared
    example, the previous example). Never someone else's check."""
    with db.connect(db_path) as conn:
        row = conn.execute(
            "SELECT p.id FROM runs r JOIN runs p ON p.store_url = r.store_url AND p.owner_hash IS r.owner_hash"
            " JOIN scores s ON s.run_id = p.id"
            " WHERE r.id = ? AND p.id < r.id AND p.status = 'completed' ORDER BY p.id DESC LIMIT 1",
            (run_id,),
        ).fetchone()
    return row[0] if row else None


def compare_runs(db_path: Path, before_id: int, after_id: int) -> dict[str, Any]:
    before, after = load_run(db_path, before_id), load_run(db_path, after_id)
    missing = [str(i) for i, r in ((before_id, before), (after_id, after)) if r is None]
    if missing:
        raise CompareError(f"No run {', '.join(missing)}")
    if not before["score"] or not after["score"]:
        raise CompareError("Both runs must be finished and scored")

    sb = {c["check_key"]: c for c in before["checks"]}
    sa = {c["check_key"]: c for c in after["checks"]}

    def item(key: str) -> dict[str, Any]:
        b, a = sb.get(key, {}), sa.get(key, {})
        fix = next((f["fix"] for f in after["scorecard"]["fixes"] if f["check"] == key), None)
        return {"check": key, "title": CHECKS[key].title, "points": CHECKS[key].points,
                "before": b.get("status", "not_tested"), "after": a.get("status", "not_tested"),
                "before_reason": b.get("reason"), "after_reason": a.get("reason"), "fix": fix}

    items = [item(k) for k in CHECKS]
    fixed = [i for i in items if i["before"] == "fail" and i["after"] == "pass"]
    remaining = [i for i in items if i["before"] == "fail" and i["after"] == "fail"]
    new = [i for i in items if i["before"] != "fail" and i["after"] == "fail"]
    newly_tested = [i for i in items if i["before"] in ("not_tested", "excluded") and i["after"] == "pass"]

    fb, fa = before["flaws_snapshot"] or {}, after["flaws_snapshot"] or {}
    flaws_fixed = sorted(k for k in fb if fb.get(k) and not fa.get(k))
    flaws_added = sorted(k for k in fa if fa.get(k) and not fb.get(k))

    warnings = []
    if before["score"]["rules_version"] != after["score"]["rules_version"]:
        warnings.append(f"Different scoring rules ({before['score']['rules_version']} vs "
                        f"{after['score']['rules_version']}); the score change is not like-for-like.")
    if before["target_product"] != after["target_product"]:
        warnings.append("The runs shopped for different products.")
    if before["checkout"] != after["checkout"]:
        warnings.append("Only one of the runs included the PayPal payment, so payment checks are not comparable.")

    tb, ta = before["score"]["total"], after["score"]["total"]
    delta = ta - tb
    headline = (f"Score {tb} -> {ta} ({'+' if delta >= 0 else ''}{delta}). "
                f"{len(fixed)} failure(s) fixed, {len(remaining)} remaining, {len(new)} new.")
    if after["outcome"] == "purchased" and after["order"]:
        o = after["order"]
        headline += f" Purchase captured: order {o['order_id']}, {o['amount']} {o['currency']}."
    return {
        "before": _summary(before), "after": _summary(after),
        "score_change": delta, "headline": headline,
        "fixed": fixed, "remaining": remaining, "new_failures": new, "newly_passing": newly_tested,
        "flaws_turned_off": flaws_fixed, "flaws_turned_on": flaws_added,
        "not_store_fault_after": after["scorecard"]["not_store_fault"],
        "warnings": warnings, "checks": items,
    }


def _summary(run: dict[str, Any]) -> dict[str, Any]:
    return {"run_id": run["id"], "score": run["score"]["total"], "possible": run["score"]["possible"],
            "outcome": run["outcome"], "checkout": bool(run["checkout"]), "started_at": run["started_at"],
            "order_id": run["order_id"]}


def last_two_finished(db_path: Path) -> tuple[int, int]:
    runs = [r for r in list_runs(db_path, limit=50) if r["status"] == "completed" and r["score"] is not None]
    if len(runs) < 2:
        raise CompareError("Need at least two finished runs")
    return runs[1]["id"], runs[0]["id"]


def main(argv: list[str] | None = None) -> int:
    import argparse

    from ..config import get_settings

    p = argparse.ArgumentParser(prog="python -m backend.app.agent.compare", description="Compare two runs")
    p.add_argument("before", nargs="?", type=int)
    p.add_argument("after", nargs="?", type=int)
    p.add_argument("--last", action="store_true", help="compare the two most recent finished runs")
    a = p.parse_args(argv)
    db_path = get_settings().database_path
    try:
        before, after = last_two_finished(db_path) if a.last or a.before is None else (a.before, a.after)
        if after is None:
            raise CompareError("Give two run ids, or --last")
        c = compare_runs(db_path, before, after)
    except CompareError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2
    print(f"Run {before} -> run {after}: {c['headline']}")
    for w in c["warnings"]:
        print(f"  WARNING: {w}")
    if c["flaws_turned_off"]:
        print(f"  Store changes: turned off {', '.join(c['flaws_turned_off'])}")
    for label, group in (("Fixed", c["fixed"]), ("Still failing", c["remaining"]), ("New failures", c["new_failures"])):
        if group:
            print(f"  {label}:")
            for i in group:
                extra = f" Fix: {i['fix']}" if label != "Fixed" and i["fix"] else ""
                print(f"    [{i['points']:>2} pts] {i['title']}{extra}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
