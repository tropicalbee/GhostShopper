"""Merchant-facing scorecard for one run: score, prioritized fixes, and what was not the store's fault.

Everything here is derived from logged checks and the failure-type registry. LLM rephrasings
(checks.fix) are shown next to the deterministic fix, never instead of it.
"""

from typing import Any

from pathlib import PurePosixPath

from .failures import ENVIRONMENT, FAILURE_TYPES, fix_for
from .plain import NOT_YOUR_FAULT, plain_fix, status_for
from .scoring import CHECKS, STAGES

LIVE_SCOPE = "live_store_browse_only"


def _evidence_summary(evidence: dict[str, Any] | None, run_id: int | None = None) -> dict[str, Any]:
    ev = evidence or {}
    out = {k: ev[k] for k in ("url", "selector", "screenshot", "status_text", "order_id", "covered_by") if ev.get(k)}
    if run_id is not None and ev.get("screenshot"):
        out["screenshot_url"] = f"/api/runs/{run_id}/files/{PurePosixPath(ev['screenshot']).name}"
    return out


def build_scorecard(run: dict[str, Any]) -> dict[str, Any] | None:
    score = run.get("score")
    if not score:
        return None
    checks = {c["check_key"]: c for c in run["checks"]}
    platform = run.get("platform") or "unknown"

    fixes = []
    for f in score["breakdown"]:
        c = checks.get(f["key"], {})
        code = c.get("code")
        fixes.append({
            "check": f["key"], "title": f["title"], "stage": f["stage"], "severity": f["severity"],
            "points": f["points"], "status": f["status"], "code": code, "reason": c.get("reason"),
            "evidence": _evidence_summary(c.get("evidence"), run.get("id")),
            "fix": fix_for(code) or f["fix"],
            "fix_explained": c.get("fix"),
            "plain": plain_fix(code, platform),
        })

    not_fault, live_scope = [], []
    caused_by = [c for c in run["checks"] if c.get("passed") == 0 and c.get("cause") == ENVIRONMENT]
    for e in score["excluded"]:
        c = checks.get(e["key"], {})
        code = c.get("code")
        ft = FAILURE_TYPES.get(code or "")
        item = {
            "check": e["key"], "title": e["title"], "points": e["points"], "code": code,
            "reason": c.get("reason"),
            "explanation": ft.fix if ft else "Not the store's fault.",
            "plain": NOT_YOUR_FAULT.get(code or "", "Not something your store controls."),
            "kind": "failed" if c.get("passed") == 0 else "not tested (blocked)",
        }
        (live_scope if code == LIVE_SCOPE else not_fault).append(item)

    possible = score.get("possible") if score.get("possible") is not None else 100
    lines = []
    if possible == 0:
        lines.append("No score: nothing the store controls could be tested in this run.")
    else:
        line = f"Readiness score {score['total']}/100"
        if possible < 100:
            nsf = sum(n["points"] for n in not_fault)
            scope = sum(n["points"] for n in live_scope)
            parts = []
            if nsf:
                parts.append(f"{nsf} excluded as not the store's fault")
            if scope:
                parts.append(f"{scope} for payment steps only tested on the demo store")
            line += f", judged on {possible} of 100 points ({'; '.join(parts)})"
        lines.append(line + ".")
    store_failed = [f for f in fixes if f["status"] == "failed"]
    if store_failed:
        lines.append(f"{len(store_failed)} store issue(s) to fix, worth {sum(f['points'] for f in store_failed)} points.")
    for c in caused_by:
        ft = FAILURE_TYPES.get(c.get("code") or "")
        blocked = [n["check"] for n in not_fault if n["kind"] != "failed"]
        if c.get("code") == LIVE_SCOPE:
            continue
        title = CHECKS[c["check_key"]].title
        msg = f"{title}: {c['reason']} {ft.fix if ft else ''}".strip()
        msg += " Excluded from the score"
        if blocked:
            msg += f", together with the check(s) it prevented: {', '.join(blocked)}"
        lines.append(msg + ".")

    status = status_for(score["total"], possible)
    top = [f for f in fixes if f["status"] == "failed" and f["plain"] and f["stage"] != "outcome"][:3]
    simple = {
        "score": score["total"],
        "label": "How easily AI shoppers can buy from your store",
        "of_what": "of what your store controls",
        "status": status["level"],
        "status_text": status["text"],
        "top_fixes": [{"check": f["check"], "points": f["points"], **f["plain"],
                       "screenshot_url": f["evidence"].get("screenshot_url")} for f in top],
        "more_fixes": max(0, len([f for f in fixes if f["status"] == "failed" and f["stage"] != "outcome"]) - len(top)),
    }
    return {
        "total": score["total"],
        "possible": possible,
        "rules_version": score["rules_version"],
        "stages": {s: score.get(s) for s in STAGES},
        "stage_possible": {s: sum(c.points for c in CHECKS.values() if c.stage == s)
                           - sum(e["points"] for e in score["excluded"] if e.get("stage") == s) for s in STAGES},
        "fixes": fixes,
        "not_store_fault": not_fault,
        "not_checked_live": live_scope,
        "summary": lines,
        "simple": simple,
        "platform": platform,
    }
