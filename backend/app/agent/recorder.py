"""Persists a shopper run: steps, check outcomes and the score. Redacts secrets before every write."""

import json
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from .. import db
from ..failures import ENVIRONMENT, NOT_TESTED_ENVIRONMENT, NOT_TESTED_STORE, STORE, cause_of
from ..scoring import CHECKS, EXCLUDED, FAIL, NOT_TESTED, PASS, Score

REDACTED = "[REDACTED]"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Redactor:
    """Replaces every occurrence of a secret value. Defense in depth: secrets should never reach here."""

    def __init__(self, secrets: Iterable[str] = ()):
        # Longest first, so a secret that contains another is fully replaced.
        self._secrets = sorted({s for s in secrets if s}, key=len, reverse=True)

    def __call__(self, text: str | None) -> str | None:
        if text is None:
            return None
        for s in self._secrets:
            text = text.replace(s, REDACTED)
        return text

    def json(self, value: Any) -> str | None:
        return None if value is None else self(json.dumps(value, default=str))


def status_of(passed: int | None, cause: str | None) -> str:
    """DB row -> scoring status. Anything not the store's fault is excluded from the score."""
    if passed == 1:
        return PASS
    if cause == ENVIRONMENT:
        return EXCLUDED
    return FAIL if passed == 0 else NOT_TESTED


class RunRecorder:
    def __init__(self, db_path: Path, run_id: int, redact: Redactor):
        self.db_path = db_path
        self.run_id = run_id
        self._redact = redact

    def redact(self, text: str) -> str:
        """Same scrubbing as the DB writes, for anything sent back to the LLM."""
        return self._redact(text) or ""

    @classmethod
    def start(
        cls,
        db_path: Path,
        *,
        store_url: str,
        goal: str,
        target_product: str,
        checkout: bool,
        paypal_mode: str,
        flaws: dict[str, bool] | None,
        llm: str,
        model: str | None,
        browser: str = "local",
        secrets: Iterable[str] = (),
    ) -> "RunRecorder":
        db.init_db(db_path)
        redact = Redactor(secrets)
        with db.connect(db_path) as conn:
            cur = conn.execute(
                "INSERT INTO runs (started_at, status, browser, store_url, goal, target_product, checkout,"
                " paypal_mode, flaws_snapshot, llm, model) VALUES (?, 'running', ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (_now(), browser, store_url, redact(goal), target_product, int(checkout), paypal_mode,
                 json.dumps(flaws) if flaws is not None else None, llm, model),
            )
            run_id = cur.lastrowid
        return cls(db_path, run_id, redact)

    def add_step(
        self,
        *,
        idx: int,
        tool: str,
        args: dict[str, Any],
        thought: str | None,
        observation: str,
        ok: bool,
        url: str | None,
        screenshot_path: str | None,
        duration_ms: int,
    ) -> int:
        with db.connect(self.db_path) as conn:
            cur = conn.execute(
                "INSERT INTO steps (run_id, idx, tool, args, thought, observation, ok, url, screenshot_path,"
                " duration_ms, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (self.run_id, idx, tool, self._redact.json(args), self._redact(thought), self._redact(observation),
                 int(ok), self._redact(url), screenshot_path, duration_ms, _now()),
            )
            return cur.lastrowid

    def record_check(
        self,
        key: str,
        passed: bool | None,
        reason: str,
        evidence: dict[str, Any] | None = None,
        step_id: int | None = None,
        code: str | None = None,
    ) -> bool:
        """First outcome per check wins. Returns False if the check was already recorded.

        The failure code decides the cause (failures.FAILURE_TYPES); passes have no cause.
        """
        check = CHECKS[key]
        cause = None if passed else cause_of(code)
        with db.connect(self.db_path) as conn:
            cur = conn.execute(
                "INSERT OR IGNORE INTO checks (run_id, step_id, check_key, stage, passed, code, cause, severity,"
                " reason, evidence, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (self.run_id, step_id, key, check.stage, None if passed is None else int(passed), code, cause,
                 check.severity, self._redact(reason), self._redact.json(evidence), _now()),
            )
            return cur.rowcount == 1

    def is_recorded(self, key: str) -> bool:
        with db.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT 1 FROM checks WHERE run_id = ? AND check_key = ?", (self.run_id, key)
            ).fetchone()
        return row is not None

    def rows(self) -> list[dict[str, Any]]:
        with db.connect(self.db_path) as conn:
            return [dict(r) for r in conn.execute(
                "SELECT check_key, passed, code, cause FROM checks WHERE run_id = ? ORDER BY id", (self.run_id,))]

    def results(self) -> dict[str, str]:
        """check key -> scoring status (pass | fail | not_tested | excluded)."""
        return {r["check_key"]: status_of(r["passed"], r["cause"]) for r in self.rows()}

    def has_environment_failure(self) -> bool:
        return any(r["passed"] == 0 and r["cause"] == ENVIRONMENT for r in self.rows())

    def mark_untested(self, reasons: dict[str, str], blocked_by_environment: bool = False) -> None:
        """Record every check that never ran as not tested. If the run was stopped by something that is
        not the store's fault, those checks are excluded rather than counted against the store."""
        code = NOT_TESTED_ENVIRONMENT if blocked_by_environment else NOT_TESTED_STORE
        for key, check in CHECKS.items():
            reason = reasons.get(check.stage, "Not tested: the agent did not reach this stage.")
            self.record_check(key, None, reason, code=code)

    def set_awaiting(self, info: dict[str, Any] | None) -> None:
        """Pause marker for human approval; None resumes the run."""
        with db.connect(self.db_path) as conn:
            conn.execute(
                "UPDATE runs SET status = ?, awaiting = ? WHERE id = ?",
                ("awaiting_human" if info else "running", self._redact.json(info), self.run_id),
            )

    def save_score(self, score: Score) -> None:
        s = score.stages
        with db.connect(self.db_path) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO scores (run_id, total, possible, discover, details, checkout, payment, outcome,"
                " breakdown, excluded, rules_version, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (self.run_id, score.total, score.possible, s["discover"][0], s["details"][0], s["checkout"][0],
                 s["payment"][0], s["outcome"][0], json.dumps([asdict(f) for f in score.fixes]),
                 json.dumps([asdict(e) for e in score.excluded]), score.rules_version, _now()),
            )

    def finish(
        self,
        *,
        status: str,
        outcome: str,
        step_count: int,
        end_reason: str | None = None,
        summary: str | None = None,
        report: dict[str, Any] | None = None,
        error: str | None = None,
    ) -> None:
        with db.connect(self.db_path) as conn:
            conn.execute(
                "UPDATE runs SET status = ?, outcome = ?, end_reason = ?, step_count = ?, agent_summary = ?,"
                " agent_report = ?, awaiting = NULL, error = ?, finished_at = ? WHERE id = ?",
                (status, outcome, end_reason, step_count, self._redact(summary), self._redact.json(report),
                 self._redact(error), _now(), self.run_id),
            )


def _loads(value: str | None) -> Any:
    return json.loads(value) if value else None


def load_run(db_path: Path, run_id: int) -> dict[str, Any] | None:
    from ..scorecard import build_scorecard

    with db.connect(db_path) as conn:
        run = conn.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
        if run is None:
            return None
        steps = conn.execute("SELECT * FROM steps WHERE run_id = ? ORDER BY idx", (run_id,)).fetchall()
        checks = conn.execute("SELECT * FROM checks WHERE run_id = ? ORDER BY id", (run_id,)).fetchall()
        score = conn.execute("SELECT * FROM scores WHERE run_id = ?", (run_id,)).fetchone()
    out = dict(run)
    for key in ("flaws_snapshot", "agent_report", "awaiting"):
        out[key] = _loads(out.get(key))
    out["steps"] = [{**dict(r), "args": _loads(r["args"])} for r in steps]
    out["checks"] = [{**dict(r), "evidence": _loads(r["evidence"]), "status": status_of(r["passed"], r["cause"])}
                     for r in checks]
    out["score"] = ({**dict(score), "breakdown": _loads(score["breakdown"]), "excluded": _loads(score["excluded"]) or []}
                    if score else None)
    out["order"] = db.get_order(db_path, run["order_id"]) if run["order_id"] else None
    out["scorecard"] = build_scorecard(out)
    return out


def list_runs(db_path: Path, limit: int = 50) -> list[dict[str, Any]]:
    with db.connect(db_path) as conn:
        rows = conn.execute(
            "SELECT r.id, r.started_at, r.finished_at, r.status, r.outcome, r.end_reason, r.llm, r.browser,"
            " r.checkout, r.paypal_mode, r.flaws_snapshot, r.step_count, r.order_id, s.total AS score,"
            " s.possible AS score_possible"
            " FROM runs r LEFT JOIN scores s ON s.run_id = r.id ORDER BY r.id DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [{**dict(r), "flaws_snapshot": _loads(r["flaws_snapshot"])} for r in rows]


__all__ = ["Redactor", "RunRecorder", "load_run", "list_runs", "status_of", "STORE", "ENVIRONMENT"]
