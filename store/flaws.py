"""Deliberate agent-readiness flaws, each behind a toggle persisted in SQLite.

All flaws default to ON so a fresh store is the "bad store" in the demo.
"""

import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator


@dataclass(frozen=True)
class Flaw:
    key: str
    label: str
    description: str


FLAWS: tuple[Flaw, ...] = (
    Flaw(
        "price_as_image",
        "Price only in an image",
        "Prices are drawn into an image with no text or alt attribute.",
    ),
    Flaw(
        "no_structured_data",
        "Missing structured product data",
        "No schema.org Product JSON-LD, no meta description, no SKU or availability in the page.",
    ),
    Flaw(
        "ambiguous_buttons",
        "Ambiguous buy buttons",
        "Several unlabeled div 'buttons' (Go, Continue, Proceed, an arrow); only one starts checkout.",
    ),
    Flaw(
        "extra_checkout_step",
        "Extra checkout step",
        "A required 'Your details' form sits between the product page and payment.",
    ),
)
FLAW_KEYS = tuple(f.key for f in FLAWS)

SCHEMA = "CREATE TABLE IF NOT EXISTS store_flaws (key TEXT PRIMARY KEY, enabled INTEGER NOT NULL)"


class FlawStore:
    def __init__(self, db_path: Path):
        self._db_path = db_path
        db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.execute(SCHEMA)
            conn.executemany(
                "INSERT OR IGNORE INTO store_flaws (key, enabled) VALUES (?, 1)", [(k,) for k in FLAW_KEYS]
            )

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self._db_path)
        try:
            with conn:  # commits on success, rolls back on error
                yield conn
        finally:
            conn.close()

    def get_all(self) -> dict[str, bool]:
        with self._connect() as conn:
            rows = conn.execute("SELECT key, enabled FROM store_flaws").fetchall()
        state = {k: True for k in FLAW_KEYS}
        state.update({k: bool(v) for k, v in rows if k in state})
        return state

    def set_many(self, updates: dict[str, bool]) -> dict[str, bool]:
        unknown = set(updates) - set(FLAW_KEYS)
        if unknown:
            raise KeyError(", ".join(sorted(unknown)))
        with self._connect() as conn:
            conn.executemany(
                "UPDATE store_flaws SET enabled = ? WHERE key = ?",
                [(int(v), k) for k, v in updates.items()],
            )
        return self.get_all()
