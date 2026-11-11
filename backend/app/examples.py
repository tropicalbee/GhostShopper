"""Bundled example checks: real runs recorded locally, shipped with the app so a fresh server is never empty.

    python -m backend.app.examples export 31 34    # copy these runs and their screenshots into backend/app/examples/

A deployed server's SQLite disk starts empty on every restart, and visitors only see their own checks plus shared
examples (owner_hash NULL). With EXAMPLE_RUNS=1 the server loads the bundled runs at startup as shared examples,
once: a run already present (same started_at, no owner) is skipped. The rows are copied as recorded, nothing is
rescored or rewritten except ids and screenshot paths.
"""

import argparse
import json
import logging
import re
import shutil
import sys
from pathlib import Path
from typing import Any

from . import db

log = logging.getLogger(__name__)

EXAMPLES_DIR = Path(__file__).with_name("examples")
MANIFEST = "examples.json"
# Sandbox account emails appear in PayPal's order and capture responses; the repo gets a placeholder instead.
SANDBOX_EMAIL_RE = re.compile(r"\bsb-[a-z0-9]+@(personal|business)\.example\.com\b", re.IGNORECASE)
# So are the sandbox payer and merchant ids and the buyer's shipping name and address.
SANDBOX_ID_KEYS = {"payer_id", "account_id", "merchant_id"}


def _blank(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: _blank(v) for k, v in value.items()}
    return "REDACTED"


def _redact_payer(value: Any) -> Any:
    """Blank the sandbox ids and shipping details, also inside the order and capture responses that the runs
    store as JSON text. The structure stays, so the JSON still parses and the trace still reads."""
    if isinstance(value, dict):
        out = {}
        for key, item in value.items():
            if key in SANDBOX_ID_KEYS and isinstance(item, str):
                out[key] = "REDACTED"
            elif key == "shipping" and isinstance(item, dict):
                out[key] = {k: _blank(v) if k in ("name", "address") else _redact_payer(v) for k, v in item.items()}
            else:
                out[key] = _redact_payer(item)
        return out
    if isinstance(value, list):
        return [_redact_payer(item) for item in value]
    if isinstance(value, str) and value[:1] in ("{", "["):
        try:
            return json.dumps(_redact_payer(json.loads(value)), ensure_ascii=False)
        except ValueError:
            return value
    return value


def _rows(conn, sql: str, *params: Any) -> list[dict[str, Any]]:
    return [dict(r) for r in conn.execute(sql, params)]


def export_runs(db_path: Path, run_ids: list[int], out_dir: Path = EXAMPLES_DIR) -> list[dict[str, Any]]:
    """Write the runs' rows to out_dir/examples.json and their screenshots to out_dir/run-<id>/."""
    examples = []
    with db.connect(db_path) as conn:
        for run_id in run_ids:
            runs = _rows(conn, "SELECT * FROM runs WHERE id = ?", run_id)
            if not runs:
                raise SystemExit(f"No run {run_id} in {db_path}")
            run = runs[0]
            if run["status"] != "completed":
                raise SystemExit(f"Run {run_id} is {run['status']}; only completed runs make examples")
            examples.append({
                "run": run,
                "steps": _rows(conn, "SELECT * FROM steps WHERE run_id = ? ORDER BY idx", run_id),
                "checks": _rows(conn, "SELECT * FROM checks WHERE run_id = ? ORDER BY id", run_id),
                "scores": _rows(conn, "SELECT * FROM scores WHERE run_id = ?", run_id),
                "orders": _rows(conn, "SELECT * FROM orders WHERE run_id = ?", run_id),
                "store_orders": _rows(conn, "SELECT * FROM store_orders WHERE run_id = ?", run_id),
            })
    out_dir.mkdir(parents=True, exist_ok=True)
    cleaned = []
    for ex in examples:
        shots = {Path(s["screenshot_path"]).parent for s in ex["steps"] if s["screenshot_path"]}
        if len(shots) > 1:
            raise SystemExit(f"Run {ex['run']['id']} has screenshots in more than one folder")
        target = out_dir / f"run-{ex['run']['id']}"
        target.mkdir(exist_ok=True)
        text = json.dumps(ex, ensure_ascii=False)
        for folder in shots:
            for png in folder.glob("*.png"):
                shutil.copy2(png, target / png.name)
            text = text.replace(folder.as_posix(), f"examples/{target.name}")  # no local paths in the repo
        cleaned.append(_redact_payer(json.loads(SANDBOX_EMAIL_RE.sub(r"sb-redacted@\1.example.com", text))))
    (out_dir / MANIFEST).write_text(json.dumps(cleaned, indent=1, ensure_ascii=False), encoding="utf-8")
    return cleaned


def _insert(conn, table: str, row: dict[str, Any]) -> int:
    cols = ", ".join(row)
    marks = ", ".join("?" for _ in row)
    return conn.execute(f"INSERT INTO {table} ({cols}) VALUES ({marks})", tuple(row.values())).lastrowid


def _move_path(value: str | None, old_folder: str | None, new_folder: Path) -> str | None:
    """Point a recorded screenshot path (or JSON text holding one) at the run's new folder."""
    if not value or not old_folder:
        return value
    return value.replace(old_folder, new_folder.as_posix())


def load_examples(db_path: Path, runs_dir: Path, src_dir: Path = EXAMPLES_DIR) -> list[int]:
    """Insert the bundled runs that are missing as shared examples. Returns the new run ids."""
    manifest = src_dir / MANIFEST
    if not manifest.is_file():
        return []
    added = []
    for ex in json.loads(manifest.read_text(encoding="utf-8")):
        src = ex["run"]
        with db.connect(db_path) as conn:
            if conn.execute("SELECT 1 FROM runs WHERE started_at = ? AND owner_hash IS NULL",
                            (src["started_at"],)).fetchone():
                continue
            # A store order number or PayPal order id already taken means this server made it; keep the server's.
            taken_store = {r[0] for r in conn.execute("SELECT number FROM store_orders")}
            taken_paypal = {r[0] for r in conn.execute("SELECT order_id FROM orders")}
            run_id = _insert(conn, "runs", {**{k: v for k, v in src.items() if k != "id"}, "owner_hash": None})
            folder = runs_dir / f"run-{run_id}"
            old_folder = next((Path(s["screenshot_path"]).parent.as_posix() for s in ex["steps"] if s["screenshot_path"]), None)
            step_ids = {}
            for step in ex["steps"]:
                new = {k: v for k, v in step.items() if k != "id"}
                new.update(run_id=run_id, screenshot_path=_move_path(step["screenshot_path"], old_folder, folder))
                step_ids[step["id"]] = _insert(conn, "steps", new)
            for check in ex["checks"]:
                new = {k: v for k, v in check.items() if k != "id"}
                new.update(run_id=run_id, step_id=step_ids.get(check["step_id"]),
                           evidence=_move_path(check["evidence"], old_folder, folder))
                _insert(conn, "checks", new)
            for score in ex["scores"]:
                _insert(conn, "scores", {**score, "run_id": run_id})
            for order in ex["orders"]:
                if order["order_id"] not in taken_paypal:
                    _insert(conn, "orders", {**order, "run_id": run_id})
            for order in ex["store_orders"]:
                if order["number"] not in taken_store:
                    _insert(conn, "store_orders", {**order, "run_id": run_id})
        folder.mkdir(parents=True, exist_ok=True)
        for png in (src_dir / f"run-{src['id']}").glob("*.png"):
            shutil.copy2(png, folder / png.name)
        added.append(run_id)
    return added


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="python -m backend.app.examples", description=__doc__.split("\n\n")[0])
    sub = p.add_subparsers(dest="command", required=True)
    exp = sub.add_parser("export", help="copy runs and their screenshots into backend/app/examples/")
    exp.add_argument("run_ids", nargs="+", type=int)
    a = p.parse_args(argv)
    from .config import get_settings

    examples = export_runs(get_settings().database_path, a.run_ids)
    for ex in examples:
        r = ex["run"]
        score = ex["scores"][0]["total"] if ex["scores"] else None
        folder = EXAMPLES_DIR / f"run-{r['id']}"
        print(f"run {r['id']}: {r['outcome']}, score {score}, {len(ex['steps'])} steps -> {folder}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
