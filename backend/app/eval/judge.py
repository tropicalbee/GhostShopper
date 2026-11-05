"""LLM-as-judge for fix explanations. A secondary quality metric only: it NEVER affects the readiness score.

For each LLM-rephrased fix it asks: does the explanation match the logged evidence, is it actionable,
is anything invented? A deterministic cross-check flags numbers in the explanation that appear nowhere
in the evidence or the deterministic fix. Ratings live in their own table (judge_ratings); judge runs
made with a replayed cassette are stored with valid = 0 ("not valid until run live").
"""

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .. import db
from ..agent.llm import LLM
from ..agent.recorder import load_run

JUDGE_SCHEMA = """
CREATE TABLE IF NOT EXISTS judge_ratings (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id           INTEGER NOT NULL,
    check_key        TEXT NOT NULL,
    code             TEXT,
    matches_evidence INTEGER,          -- 1-5
    actionable       INTEGER,          -- 1-5
    invented         INTEGER,          -- 1 = the judge says something was made up
    invented_numbers TEXT,             -- JSON: deterministic cross-check
    notes            TEXT,
    judge_model      TEXT NOT NULL,
    valid            INTEGER NOT NULL, -- 0 = replayed cassette, not a real judgement
    created_at       TEXT NOT NULL
);
"""
SYSTEM = (
    "You review explanations of website fixes written for a small-shop owner. For each item compare the "
    "explanation with the evidence and the reference fix. Rate matches_evidence (1-5: does it describe the "
    "problem the evidence shows?), actionable (1-5: could the owner act on it?), and invented (true if it adds "
    "facts, numbers, tools or steps that are not in the evidence or reference fix). Reply with only a JSON object "
    "mapping each code to {\"matches_evidence\": n, \"actionable\": n, \"invented\": bool, \"notes\": \"...\"}."
)
NUMBER_RE = re.compile(r"\d+(?:\.\d+)?")


def invented_numbers(explanation: str, sources: list[str]) -> list[str]:
    """Numbers in the explanation that appear in none of the source texts."""
    known = set(NUMBER_RE.findall(" ".join(sources)))
    return sorted({n for n in NUMBER_RE.findall(explanation) if n not in known})


def _rating(value: Any, lo: int = 1, hi: int = 5) -> int | None:
    return value if isinstance(value, int) and lo <= value <= hi else None


def parse_ratings(content: str | None, codes: set[str]) -> dict[str, dict[str, Any]]:
    if not content:
        return {}
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", content.strip())
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return {}
    out = {}
    for code, r in (data.items() if isinstance(data, dict) else []):
        if code in codes and isinstance(r, dict):
            out[code] = {"matches_evidence": _rating(r.get("matches_evidence")), "actionable": _rating(r.get("actionable")),
                         "invented": r.get("invented") if isinstance(r.get("invented"), bool) else None,
                         "notes": str(r.get("notes", ""))[:300]}
    return out


async def judge_run(db_path: Path, run_id: int, llm: LLM) -> dict[str, Any]:
    run = load_run(db_path, run_id)
    if run is None:
        raise LookupError(f"No run {run_id}")
    items = [f for f in run["scorecard"]["fixes"] if f["status"] == "failed" and f.get("fix_explained")]
    valid = llm.kind == "groq"
    note = None if valid else "Not valid until run live: this judgement replayed a recorded cassette."
    if not items:
        return {"run_id": run_id, "valid": valid, "note": "No LLM explanations to judge; run explain first.",
                "items": [], "summary": None}
    payload = [{"code": f["code"], "evidence": {"reason": f["reason"], **f["evidence"]}, "reference_fix": f["fix"],
                "explanation": f["fix_explained"]} for f in items]
    reply = await llm.complete([{"role": "system", "content": SYSTEM},
                                {"role": "user", "content": json.dumps(payload, indent=2)}], [])
    ratings = parse_ratings(reply.content, {f["code"] for f in items})
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    out_items = []
    db.init_db(db_path)
    with db.connect(db_path) as conn:
        conn.executescript(JUDGE_SCHEMA)
        for f in items:
            r = ratings.get(f["code"], {})
            nums = invented_numbers(f["fix_explained"], [f["reason"] or "", f["fix"], json.dumps(f["evidence"])])
            conn.execute(
                "INSERT INTO judge_ratings (run_id, check_key, code, matches_evidence, actionable, invented,"
                " invented_numbers, notes, judge_model, valid, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (run_id, f["check"], f["code"], r.get("matches_evidence"), r.get("actionable"),
                 None if r.get("invented") is None else int(r["invented"]), json.dumps(nums), r.get("notes"),
                 llm.model or llm.kind, int(valid), now))
            out_items.append({"check": f["check"], "code": f["code"], **r, "invented_numbers": nums,
                              "rated": bool(r)})
    rated = [i for i in out_items if i["rated"]]

    def mean(key: str) -> float | None:
        vals = [i[key] for i in rated if i.get(key) is not None]
        return round(sum(vals) / len(vals), 2) if vals else None

    summary = {"rated": len(rated), "unrated": len(out_items) - len(rated),
               "mean_matches_evidence": mean("matches_evidence"), "mean_actionable": mean("actionable"),
               "invented_rate": round(sum(1 for i in rated if i.get("invented")) / len(rated), 2) if rated else None,
               "explanations_with_unsourced_numbers": sum(1 for i in out_items if i["invented_numbers"])}
    return {"run_id": run_id, "valid": valid, "note": note, "judge_model": llm.model, "items": out_items,
            "summary": summary}
