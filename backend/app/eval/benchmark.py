"""Detection benchmark: inject flaw combinations, run the shopper, compare failed checks with ground truth.

Each worker owns its own store server and SQLite file (flaws are per store), all with PAYPAL_MODE=mock.
Navigation is done by the scripted navigator, so the numbers measure the deterministic detectors.
"""

import asyncio
import json
import time
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..agent.loop import DEFAULT_TARGET, RunConfig, run_shopper
from ..agent.paypal_flow import make_payment_handler
from ..agent.recorder import load_run
from ..agent.service import apply_flaws
from ..config import REPO_ROOT, Settings
from .ground_truth import DETECTOR_CHECKS, expected
from .navigator import ScriptedNavigator
from .server import LiveServer


@dataclass
class RunResult:
    combo: list[str]
    run_id: int
    worker: int
    outcome: str
    score: int
    seconds: float
    expected: list[str]
    masked: list[str]
    detected: list[str]
    tp: list[str]
    fp: list[str]
    fn: list[str]
    collateral: list[str]  # non-detector checks that failed (e.g. checkout_reached), reported separately
    per_flaw: dict[str, dict[str, Any]] = field(default_factory=dict)


async def run_combo(srv: LiveServer, db_path: Path, runs_dir: Path, combo: tuple[str, ...], worker: int,
                    checkout: bool, max_steps: int) -> RunResult:
    store_url = f"{srv.url}/store/"
    snapshot = await apply_flaws(store_url, ",".join(combo) if combo else "off")
    payment = make_payment_handler("mock", store_url, "mock", True) if checkout else None
    cfg = RunConfig(store_url=store_url, db_path=db_path, flaws=snapshot, checkout=checkout,
                    paypal_mode="mock" if checkout else "off", max_steps=max_steps, runs_dir=runs_dir)
    started = time.monotonic()
    run_id = await run_shopper(cfg, ScriptedNavigator(DEFAULT_TARGET), payment)
    seconds = time.monotonic() - started
    run = load_run(db_path, run_id)
    failed = {c["check_key"] for c in run["checks"] if c["status"] == "fail"}
    detected = failed & set(DETECTOR_CHECKS)
    truth = expected(set(combo), checkout)
    exp, masked = truth.all_expected, truth.all_masked
    per_flaw = {}
    for flaw in combo:
        labels = truth.expected.get(flaw, set())
        per_flaw[flaw] = {"expected": sorted(labels), "missed": sorted(labels - detected),
                          "masked": sorted(truth.masked.get(flaw, set()) - labels)}
    return RunResult(
        combo=list(combo), run_id=run_id, worker=worker, outcome=run["outcome"], score=run["score"]["total"],
        seconds=round(seconds, 1), expected=sorted(exp), masked=sorted(masked), detected=sorted(detected),
        tp=sorted(detected & exp), fp=sorted(detected - exp - masked), fn=sorted(exp - detected),
        collateral=sorted(failed - set(DETECTOR_CHECKS)), per_flaw=per_flaw)


async def run_benchmark(combos: list[tuple[str, ...]], *, workers: int = 4, checkout: bool = True,
                        max_steps: int = 45, out_dir: Path | None = None, label: str = "benchmark") -> dict[str, Any]:
    from ..main import create_app

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_dir = out_dir or REPO_ROOT / "data" / "eval" / f"{label}-{stamp}"
    out_dir.mkdir(parents=True, exist_ok=True)
    queue: asyncio.Queue[tuple[str, ...]] = asyncio.Queue()
    for c in combos:
        queue.put_nowait(c)
    results: list[RunResult] = []
    errors: list[dict[str, Any]] = []

    async def worker(i: int) -> None:
        db_path = out_dir / f"worker{i}.db"
        settings = Settings("", "", db_path, "http://unused", paypal_mode="mock", dev_options=True)  # local only
        with LiveServer(create_app(settings)) as srv:
            while not queue.empty():
                combo = queue.get_nowait()
                try:
                    results.append(await run_combo(srv, db_path, out_dir / "runs", combo, i, checkout, max_steps))
                except Exception as exc:  # recorded, never silently dropped
                    errors.append({"combo": list(combo), "worker": i, "error": f"{type(exc).__name__}: {exc}"[:300]})

    started = time.monotonic()
    await asyncio.gather(*(worker(i) for i in range(max(1, min(workers, len(combos))))))
    report = summarize(results, errors, checkout=checkout, label=label, seconds=time.monotonic() - started)
    report["out_dir"] = str(out_dir)
    (out_dir / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


def _ratio(a: int, b: int) -> float | None:
    return round(a / b, 3) if b else None


def summarize(results: list[RunResult], errors: list[dict[str, Any]], *, checkout: bool, label: str,
              seconds: float) -> dict[str, Any]:
    tp = sum(len(r.tp) for r in results)
    fp = sum(len(r.fp) for r in results)
    fn = sum(len(r.fn) for r in results)
    per_check = defaultdict(lambda: Counter())
    for r in results:
        for k in r.tp:
            per_check[k]["tp"] += 1
        for k in r.fp:
            per_check[k]["fp"] += 1
        for k in r.fn:
            per_check[k]["fn"] += 1
    per_flaw: dict[str, Counter] = defaultdict(Counter)
    missed_detail: dict[str, Counter] = defaultdict(Counter)
    for r in results:
        for flaw, info in r.per_flaw.items():
            per_flaw[flaw]["runs"] += 1
            if not info["expected"]:
                per_flaw[flaw]["fully_masked"] += 1
            elif info["missed"]:
                per_flaw[flaw]["missed"] += 1
                for k in info["missed"]:
                    missed_detail[flaw][k] += 1
            else:
                per_flaw[flaw]["detected"] += 1
    return {
        "label": label,
        "checkout_runs": checkout,
        "navigator": "scripted-navigator-v1 (rule-based, not an LLM)",
        "runs": len(results),
        "errors": errors,
        "seconds": round(seconds, 1),
        "micro": {"tp": tp, "fp": fp, "fn": fn, "precision": _ratio(tp, tp + fp), "recall": _ratio(tp, tp + fn)},
        "per_check": {k: {**v, "precision": _ratio(v["tp"], v["tp"] + v["fp"]), "recall": _ratio(v["tp"], v["tp"] + v["fn"])}
                      for k, v in sorted(per_check.items())},
        "per_flaw": {k: {**v, "missed_checks": dict(missed_detail[k])} for k, v in sorted(per_flaw.items())},
        "outcomes": dict(Counter(r.outcome for r in results)),
        "collateral": dict(Counter(k for r in results for k in r.collateral)),
        "mean_seconds_per_run": round(sum(r.seconds for r in results) / len(results), 1) if results else None,
        "results": [asdict(r) for r in results],
    }


def markdown(report: dict[str, Any]) -> str:
    m = report["micro"]
    lines = [
        f"**{report['label']}**: {report['runs']} runs ({'checkout' if report['checkout_runs'] else 'browse'}), "
        f"{report['navigator']}, {report['seconds']}s total, {report['mean_seconds_per_run']}s/run, "
        f"errors: {len(report['errors'])}.",
        "",
        f"Micro precision **{m['precision']}**, recall **{m['recall']}** (TP {m['tp']}, FP {m['fp']}, FN {m['fn']}).",
        "",
        "| Flaw | Runs | Detected | Missed | Fully masked | Missed checks |",
        "|---|---|---|---|---|---|",
    ]
    for flaw, v in report["per_flaw"].items():
        missed = ", ".join(f"{k} x{n}" for k, n in v["missed_checks"].items()) or "-"
        lines.append(f"| {flaw} | {v.get('runs', 0)} | {v.get('detected', 0)} | {v.get('missed', 0)} | "
                     f"{v.get('fully_masked', 0)} | {missed} |")
    lines += ["", f"Outcomes: {report['outcomes']}. Collateral failures (not detector checks): {report['collateral'] or 'none'}."]
    fps = {k: v["fp"] for k, v in report["per_check"].items() if v.get("fp")}
    lines.append(f"False positives by check: {fps or 'none'}.")
    return "\n".join(lines)
