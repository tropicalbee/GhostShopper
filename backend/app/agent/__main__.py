"""Run the mystery shopper from the command line against a running store.

    python -m backend.app.agent --llm mock --cassette day2_flaws_on --flaws on
    python -m backend.app.agent --llm live --flaws off --record my_run
"""

import argparse
import asyncio
import json
import sys

from ..config import get_settings
from .recorder import load_run
from .service import RunConfigError, RunRequest, execute, resolve_target
from .site import allow_private_hosts


def print_awaiting_human(info: dict, popup) -> None:
    """Human-approval notice. The agent never tries to get past PayPal's checks itself."""
    print("\n*** AWAITING HUMAN APPROVAL ***", file=sys.stderr)
    print(f"    {info['reason']}", file=sys.stderr)
    if info.get("live_view_url"):
        print(f"    Open the Kernel live view and complete the PayPal window: {info['live_view_url']}", file=sys.stderr)
    elif info.get("headless", True):
        print("    The browser is headless, so nobody can complete it. Rerun with --headed to approve by hand.",
              file=sys.stderr)
    else:
        print("    Complete the PayPal window in the open browser.", file=sys.stderr)
    print(f"    Waiting up to {info['timeout_s']:.0f}s; the run resumes when the window closes.\n", file=sys.stderr)


def print_run(run: dict) -> None:
    card = run["scorecard"] or {}
    print(f"Run {run['id']}: status={run['status']} outcome={run['outcome']} end={run['end_reason']} "
          f"steps={run['step_count']} browser={run['browser']} platform={run.get('platform')}"
          f"{' (live store: browse-only, no payment)' if run.get('live') else ''}")
    for line in card.get("summary", []):
        print(f"  {line}")
    marks = {"pass": "PASS", "fail": "FAIL", "not_tested": "----", "excluded": "EXCL"}
    for c in run["checks"]:
        print(f"  {marks[c['status']]} {c['check_key']:<20} {c['reason']}")
    if card.get("fixes"):
        print("  Fixes, most points first:")
        for f in card["fixes"]:
            if f["status"] == "failed":
                print(f"    [{f['points']:>2} pts] {f['title']}: {f['fix']}")
    if run["order"]:
        print("  order:", json.dumps(run["order"]))
    if run["error"]:
        print("  error:", run["error"])


def main() -> int:
    p = argparse.ArgumentParser(prog="python -m backend.app.agent", description="GhostShopper mystery shopper")
    p.add_argument("--url", help="a store link to check (browse-only, never pays); default: the demo store")
    p.add_argument("--llm", choices=["live", "mock", "scripted"], default="live",
                   help="live = the provider set by LLM_PROVIDER/LLM_MODEL/LLM_API_KEY; "
                        "mock = replay a cassette; scripted = rule-based navigator (not an LLM), works on any store")
    p.add_argument("--cassette", help="mock: name of the recorded responses to replay")
    p.add_argument("--record", help="live: save this run's LLM replies as a cassette with this name")
    p.add_argument("--flaws", default="keep",
                   help="set store flaws before the run: on (the 4 classic flaws), off, all, keep, "
                        "or a comma-separated list of flaw keys")
    p.add_argument("--checkout", action="store_true", help="also pay with PayPal")
    p.add_argument("--paypal", choices=["mock", "sandbox"], default="sandbox",
                   help="checkout mode; must match the server's PAYPAL_MODE")
    p.add_argument("--payment", choices=["popup", "vault"], default="popup",
                   help="popup = click the PayPal button and log in as the buyer; vault = pay with the buyer's saved "
                        "PayPal account, no popup or password (run `python -m backend.app.vault setup` once first)")
    p.add_argument("--browser", choices=["local", "kernel"], help="default: BROWSER_PROVIDER, else local")
    p.add_argument("--store-url", help="default: APP_BASE_URL + /store/")
    p.add_argument("--budget", help="spending limit in USD, like 30.00; the shopper won't pay a checkout total above it")
    p.add_argument("--max-steps", type=int, default=25)
    p.add_argument("--headed", action="store_true", help="show the browser window (needed for human approval locally)")
    a = p.parse_args()

    settings = get_settings()
    store_url = a.store_url or f"{settings.app_base_url}/store/"
    req = RunRequest(llm=a.llm, cassette=a.cassette, record=a.record, flaws=a.flaws, checkout=a.checkout,
                     paypal=a.paypal, payment=a.payment, max_steps=a.max_steps, headless=not a.headed, browser=a.browser,
                     store_url=a.url, budget=a.budget)

    async def go() -> int:
        target = await resolve_target(req, settings.app_base_url) if a.url else None
        url = target.url if target else store_url
        live = bool(target and not target.demo)
        return await execute(req, url, settings.database_path, on_awaiting_human=print_awaiting_human, live=live,
                             allow_private=allow_private_hosts(settings.app_base_url))

    try:
        run_id = asyncio.run(go())
    except RunConfigError as exc:
        print(f"Config error: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        # asyncio.run cancels the run first, so the browser and any Kernel session were closed on the way out.
        print("Interrupted: the run was stopped and its browser session closed.", file=sys.stderr)
        return 130

    run = load_run(settings.database_path, run_id)
    print_run(run)
    return 0 if run["status"] == "completed" else 1


if __name__ == "__main__":
    sys.exit(main())
