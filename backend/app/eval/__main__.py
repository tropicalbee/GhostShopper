"""Evaluation CLI.

    python -m backend.app.eval benchmark --matrix classic            # 16 combos of the 4 original flaws
    python -m backend.app.eval benchmark --matrix random --n 30 --seed 7
    python -m backend.app.eval propose --llm mock --cassette flaw_ideas
    python -m backend.app.eval judge 4 --llm mock --cassette judge_classic
"""

import argparse
import asyncio
import json
import sys

from ..agent.llm import LLMConfigError, make_llm
from ..config import get_settings


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="python -m backend.app.eval")
    sub = p.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("benchmark", help="detection precision/recall over flaw combinations")
    b.add_argument("--matrix", choices=["classic", "random"], default="classic")
    b.add_argument("--n", type=int, default=30)
    b.add_argument("--seed", type=int, default=7)
    b.add_argument("--workers", type=int, default=4)
    b.add_argument("--browse", action="store_true", help="browse-only runs (no PayPal checks)")
    pr = sub.add_parser("propose", help="ask the LLM for new flaw ideas (stored as proposals, not counted)")
    j = sub.add_parser("judge", help="LLM-as-judge on a run's fix explanations (secondary metric)")
    j.add_argument("run_id", type=int)
    for sp in (pr, j):
        sp.add_argument("--llm", choices=["live", "groq", "mock"], default="live",
                        help="live = the provider set by LLM_PROVIDER/LLM_MODEL/LLM_API_KEY (groq is an alias)")
        sp.add_argument("--cassette")
    a = p.parse_args(argv)

    if a.cmd == "benchmark":
        from .benchmark import markdown, run_benchmark
        from .saboteur import classic_matrix, random_combos

        combos = classic_matrix() if a.matrix == "classic" else random_combos(a.n, a.seed)
        label = "classic-16" if a.matrix == "classic" else f"random-{a.n}-seed{a.seed}"
        report = asyncio.run(run_benchmark(combos, workers=a.workers, checkout=not a.browse, label=label))
        print(markdown(report))
        print(f"\nFull report: {report['out_dir']}/report.json")
        return 0 if not report["errors"] else 1

    try:
        llm = make_llm(a.llm, a.cassette)
    except LLMConfigError as exc:
        print(f"Config error: {exc}", file=sys.stderr)
        return 2
    db_path = get_settings().database_path
    if a.cmd == "propose":
        from .saboteur import propose_flaws

        for prop in asyncio.run(propose_flaws(llm, db_path)):
            print(f"[{prop.status}] {prop.key}: {prop.description} -> {', '.join(prop.expected_checks) or '?'}")
        return 0
    from .judge import judge_run

    print(json.dumps(asyncio.run(judge_run(db_path, a.run_id, llm)), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
