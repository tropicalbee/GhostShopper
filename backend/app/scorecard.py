"""Merchant-facing scorecard for one run: score, prioritized fixes, and what was not the store's fault.

Everything here is derived from logged checks and the failure-type registry. LLM rephrasings
(checks.fix) are shown next to the deterministic fix, never instead of it.
"""

from typing import Any

from .failures import ENVIRONMENT, FAILURE_TYPES, fix_for
from .scoring import CHECKS


def _evidence_summary(evidence: dict[str, Any] | None) -> dict[str, Any]:
    ev = evidence or {}
    return {k: ev[k] for k in ("url", "selector", "screenshot", "status_text", "order_id") if ev.get(k)}


def build_scorecard(run: dict[str, Any]) -> dict[str, Any] | None:
    score = run.get("score")
    if not score:
        return None
    checks = {c["check_key"]: c for c in run["checks"]}

    fixes = []
    for f in score["breakdown"]:
        c = checks.get(f["key"], {})
        code = c.get("code")
        fixes.append({
            "check": f["key"], "title": f["title"], "stage": f["stage"], "severity": f["severity"],
            "points": f["points"], "status": f["status"], "code": code, "reason": c.get("reason"),
            "evidence": _evidence_summary(c.get("evidence")),
            "fix": fix_for(code) or f["fix"],
            "fix_explained": c.get("fix"),
        })

    not_fault = []
    caused_by = [c for c in run["checks"] if c.get("passed") == 0 and c.get("cause") == ENVIRONMENT]
    for e in score["excluded"]:
        c = checks.get(e["key"], {})
        ft = FAILURE_TYPES.get(c.get("code") or "")
        not_fault.append({
            "check": e["key"], "title": e["title"], "points": e["points"], "code": c.get("code"),
            "reason": c.get("reason"),
            "explanation": ft.fix if ft else "Not the store's fault.",
            "kind": "failed" if c.get("passed") == 0 else "not tested (blocked)",
        })

    possible = score.get("possible") if score.get("possible") is not None else 100
    lines = []
    if possible == 0:
        lines.append("No score: nothing the store controls could be tested in this run.")
    else:
        line = f"Readiness score {score['total']}/100"
        if possible < 100:
            line += f", judged on {possible} of 100 points ({100 - possible} excluded as not the store's fault)"
        lines.append(line + ".")
    store_failed = [f for f in fixes if f["status"] == "failed"]
    if store_failed:
        lines.append(f"{len(store_failed)} store issue(s) to fix, worth {sum(f['points'] for f in store_failed)} points.")
    for c in caused_by:
        ft = FAILURE_TYPES.get(c.get("code") or "")
        blocked = [n["check"] for n in not_fault if n["kind"] != "failed"]
        title = CHECKS[c["check_key"]].title
        msg = f"{title}: {c['reason']} {ft.fix if ft else ''}".strip()
        msg += " Excluded from the score"
        if blocked:
            msg += f", together with the check(s) it prevented: {', '.join(blocked)}"
        lines.append(msg + ".")

    return {
        "total": score["total"],
        "possible": possible,
        "rules_version": score["rules_version"],
        "stages": {s: score.get(s) for s in ("discover", "details", "checkout", "payment", "outcome")},
        "fixes": fixes,
        "not_store_fault": not_fault,
        "summary": lines,
    }
