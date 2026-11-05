"""Run the mystery shopper from the command line against a running store.

    python -m backend.app.agent --llm mock --cassette day2_flaws_on --flaws on
    python -m backend.app.agent --llm groq --flaws off --record my_run
"""

import argparse
import asyncio
import json
import sys

from ..config import get_settings
from .recorder import load_run
from .service import RunConfigError, RunRequest, execute


def main() -> int:
    p = argparse.ArgumentParser(prog="python -m backend.app.agent", description="GhostShopper mystery shopper")
    p.add_argument("--llm", choices=["mock", "groq"], default="groq")
    p.add_argument("--cassette", help="mock: name of the recorded responses to replay")
    p.add_argument("--record", help="groq: save this run's LLM replies as a cassette with this name")
    p.add_argument("--flaws", choices=["on", "off", "keep"], default="keep", help="set all store flaws before the run")
    p.add_argument("--checkout", action="store_true", help="also pay with PayPal (Day 3)")
    p.add_argument("--paypal", choices=["mock", "sandbox"], default="sandbox",
                   help="checkout mode; must match the server's PAYPAL_MODE")
    p.add_argument("--store-url", help="default: APP_BASE_URL + /store/")
    p.add_argument("--max-steps", type=int, default=25)
    p.add_argument("--headed", action="store_true", help="show the browser window")
    a = p.parse_args()

    settings = get_settings()
    store_url = a.store_url or f"{settings.app_base_url}/store/"
    req = RunRequest(llm=a.llm, cassette=a.cassette, record=a.record, flaws=a.flaws, checkout=a.checkout,
                     paypal=a.paypal, max_steps=a.max_steps, headless=not a.headed)
    try:
        run_id = asyncio.run(execute(req, store_url, settings.database_path))
    except RunConfigError as exc:
        print(f"Config error: {exc}", file=sys.stderr)
        return 2

    run = load_run(settings.database_path, run_id)
    score = run["score"]
    print(f"Run {run_id}: status={run['status']} outcome={run['outcome']} steps={run['step_count']} "
          f"score={score['total'] if score else '-'}")
    for c in run["checks"]:
        mark = {1: "PASS", 0: "FAIL", None: "----"}[c["passed"]]
        print(f"  {mark} {c['check_key']:<20} {c['reason']}")
    if run["order"]:
        print("  order:", json.dumps(run["order"]))
    if run["error"]:
        print("  error:", run["error"])
    return 0 if run["status"] == "completed" else 1


if __name__ == "__main__":
    sys.exit(main())
