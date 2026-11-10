"""The purchase trace benchmark (backend/app/eval/trace_matrix.py) on a representative subset: the healthy runs, one
scenario per purchase flaw, the price and capture-amount cases, one control, and every link-integrity case. The full
matrix is `python -m backend.app.eval benchmark --matrix trace`."""

import pytest

from backend.app.eval.trace_matrix import run_trace_matrix
from backend.app.eval.trace_truth import CASES

from .test_agent_e2e import requires_browser

pytestmark = pytest.mark.anyio

SUBSET = {
    "healthy-captured", "healthy-retry", "healthy-declined", "healthy-cancelled",
    "never_marks_paid-captured", "declined_marked_paid-declined", "success_after_cancel-cancelled",
    "duplicate_on_retry-retry", "price_mismatch-captured", "healthy-capture_amount", "never_marks_paid-declined",
}
# Scenarios the trace gets wrong today, with the reason. They stay failing in the benchmark and are listed here so the
# suite stays green. Empty now: every scenario passes, so a failure is a regression.
KNOWN_FAILURES: dict[str, str] = {}


@requires_browser
async def test_trace_matrix_subset_matches_the_hand_written_expectations(tmp_path):
    cases = tuple(c for c in CASES if c.id in SUBSET or c.category == "links")
    report = await run_trace_matrix(cases, workers=4, out_dir=tmp_path / "trace")
    assert report["errors"] == []
    assert len(report["results"]) == len(cases)
    failing = {r["id"] for r in report["results"] if not r["passed"]}
    assert failing == set(KNOWN_FAILURES) & {c.id for c in cases}, [
        (r["id"], r["expected"], r["actual"], r["actual_links"]) for r in report["results"] if not r["passed"]]
    assert report["healthy"]["false_mismatches"] == 0
