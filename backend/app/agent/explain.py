"""Optional LLM rephrasing of fix suggestions. The fix itself is deterministic (failures.FAILURE_TYPES);
the LLM only rewords it for a shop owner. Its text is stored in checks.fix, which the score never reads.

    python -m backend.app.agent.explain 4 --llm mock --cassette fixes_rephrase_classic
"""

import json
import re
import sys
from pathlib import Path
from typing import Any

from .. import db
from .llm import LLM
from .recorder import invalidate_run, load_run

MAX_LEN = 500
SYSTEM = (
    "You rewrite website fix instructions for a small-shop owner who is not a developer. "
    "Keep exactly the same action. Do not add steps, tools, numbers, prices or claims that are not in the input. "
    "One or two plain sentences each. Reply with only a JSON object mapping each code to its rewritten text."
)


def fixes_to_explain(run: dict[str, Any]) -> list[dict[str, Any]]:
    """Store-caused failures only: those are the ones the merchant acts on."""
    return [{"code": f["code"], "check": f["check"], "title": f["title"], "reason": f["reason"], "fix": f["fix"]}
            for f in run["scorecard"]["fixes"] if f["status"] == "failed" and f["code"]]


def parse_rephrasings(content: str | None, codes: set[str]) -> dict[str, str]:
    """Accept only {code: non-empty text <= MAX_LEN} for codes we asked about. Everything else is dropped."""
    if not content:
        return {}
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", content.strip())
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return {}
    if not isinstance(data, dict):
        return {}
    return {k: v.strip() for k, v in data.items()
            if k in codes and isinstance(v, str) and v.strip() and len(v.strip()) <= MAX_LEN}


async def explain_run(db_path: Path, run_id: int, llm: LLM) -> list[dict[str, Any]]:
    run = load_run(db_path, run_id)
    if run is None:
        raise LookupError(f"No run {run_id}")
    items = fixes_to_explain(run)
    if not items:
        return []
    messages = [{"role": "system", "content": SYSTEM},
                {"role": "user", "content": json.dumps(items, indent=2)}]
    reply = await llm.complete(messages, [])
    rephrased = parse_rephrasings(reply.content, {i["code"] for i in items})
    out = []
    with db.connect(db_path) as conn:
        for i in items:
            text = rephrased.get(i["code"])
            if text:
                conn.execute("UPDATE checks SET fix = ? WHERE run_id = ? AND check_key = ?", (text, run_id, i["check"]))
            out.append({**i, "explained": text or i["fix"], "source": f"llm:{llm.model}" if text else "deterministic"})
    invalidate_run(db_path, run_id)  # the cached run payload carries checks.fix
    return out


def main(argv: list[str] | None = None) -> int:
    import argparse
    import asyncio

    from ..config import get_settings
    from .llm import LLMConfigError, make_llm

    p = argparse.ArgumentParser(prog="python -m backend.app.agent.explain", description="Rephrase a run's fixes")
    p.add_argument("run_id", type=int)
    p.add_argument("--llm", choices=["live", "groq", "mock"], default="live",
                   help="live = the provider set by LLM_PROVIDER/LLM_MODEL/LLM_API_KEY (groq is an alias)")
    p.add_argument("--cassette")
    a = p.parse_args(argv)
    try:
        llm = make_llm(a.llm, a.cassette)
    except LLMConfigError as exc:
        print(f"Config error: {exc}", file=sys.stderr)
        return 2
    for item in asyncio.run(explain_run(get_settings().database_path, a.run_id, llm)):
        print(f"[{item['source']}] {item['title']}\n    fix:       {item['fix']}\n    explained: {item['explained']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
