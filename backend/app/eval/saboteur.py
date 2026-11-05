"""The saboteur: picks flaw combinations to inject into the store, and collects LLM ideas for new flaws.

A flaw only counts in evaluation once it is a store toggle with a ground-truth label. LLM proposals are
stored as ideas (status "proposed") until someone implements them; they never enter a benchmark.
"""

import itertools
import json
import random
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

from store.flaws import CLASSIC_FLAWS, FLAW_KEYS

from .. import db
from ..agent.llm import LLM
from .ground_truth import DETECTOR_CHECKS, LABELS

PROPOSALS_SCHEMA = """
CREATE TABLE IF NOT EXISTS flaw_proposals (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    key             TEXT NOT NULL,
    description     TEXT NOT NULL,
    expected_checks TEXT,          -- JSON list proposed by the LLM
    status          TEXT NOT NULL, -- implemented | proposed (not counted until implemented + labelled)
    source          TEXT NOT NULL, -- LLM model or cassette
    created_at      TEXT NOT NULL
);
"""


def implemented_flaws() -> tuple[str, ...]:
    """Flaws that are both a store toggle and labelled with ground truth."""
    return tuple(k for k in FLAW_KEYS if k in LABELS)


def classic_matrix() -> list[tuple[str, ...]]:
    """All 16 combinations of the 4 original flaws, including none: the fixed benchmark."""
    return [combo for r in range(len(CLASSIC_FLAWS) + 1) for combo in itertools.combinations(CLASSIC_FLAWS, r)]


def random_combos(n: int, seed: int, min_k: int = 1, max_k: int = 4) -> list[tuple[str, ...]]:
    """n distinct random combinations of implemented flaws (seeded, so a benchmark can be rerun)."""
    pool = implemented_flaws()
    rng = random.Random(seed)
    seen: set[tuple[str, ...]] = set()
    out: list[tuple[str, ...]] = []
    attempts = 0
    while len(out) < n and attempts < n * 50:
        attempts += 1
        k = rng.randint(min_k, min(max_k, len(pool)))
        combo = tuple(sorted(rng.sample(pool, k)))
        if combo not in seen:
            seen.add(combo)
            out.append(combo)
    return out


@dataclass(frozen=True)
class Proposal:
    key: str
    description: str
    expected_checks: list[str]
    status: str


PROPOSE_SYSTEM = (
    "You red-team online stores for AI shopping agents. Propose new realistic store flaws that would stop an "
    "agent from finding, understanding or buying a product. For each, give a snake_case key, a one-sentence "
    "description, and which of these checks it should trigger: " + ", ".join(DETECTOR_CHECKS) + ". "
    "Reply with only a JSON list of objects with keys: key, description, expected_checks."
)


def parse_proposals(content: str | None) -> list[Proposal]:
    if not content:
        return []
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", content.strip())
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return []
    out = []
    for item in data if isinstance(data, list) else []:
        if not isinstance(item, dict) or not re.fullmatch(r"[a-z][a-z0-9_]{2,40}", str(item.get("key", ""))):
            continue
        checks = [c for c in item.get("expected_checks") or [] if c in DETECTOR_CHECKS]
        status = "implemented" if item["key"] in LABELS else "proposed"
        out.append(Proposal(item["key"], str(item.get("description", ""))[:300], checks, status))
    return out


async def propose_flaws(llm: LLM, db_path: Path) -> list[Proposal]:
    reply = await llm.complete([{"role": "system", "content": PROPOSE_SYSTEM},
                                {"role": "user", "content": "Already implemented: " + ", ".join(LABELS)}], [])
    proposals = parse_proposals(reply.content)
    db.init_db(db_path)
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with db.connect(db_path) as conn:
        conn.executescript(PROPOSALS_SCHEMA)
        conn.executemany(
            "INSERT INTO flaw_proposals (key, description, expected_checks, status, source, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            [(p.key, p.description, json.dumps(p.expected_checks), p.status, llm.model or llm.kind, now)
             for p in proposals])
    return proposals


__all__ = ["Proposal", "classic_matrix", "random_combos", "implemented_flaws", "propose_flaws",
           "parse_proposals", "asdict"]
