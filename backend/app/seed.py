"""Put the app in the exact demo state in one go.

    python -m backend.app.seed                 # bad store: the 4 classic flaws on, the rest off
    python -m backend.app.seed --with-runs     # also record a before/after pair (needs a PAYPAL_MODE=mock server)

Never deletes anything: earlier runs stay in the database; the demo just uses the newest ones.
"""

import argparse
import asyncio
import sys

import httpx

from store.flaws import CLASSIC_FLAWS, FLAW_KEYS, FlawStore

from . import db
from .config import get_settings


def bad_store_flaws() -> dict[str, bool]:
    return {k: k in CLASSIC_FLAWS for k in FLAW_KEYS}


def server_health(base_url: str) -> dict | None:
    try:
        return httpx.get(f"{base_url}/api/health", timeout=5.0).json()
    except (httpx.HTTPError, ValueError):
        return None


async def record_before_after(store_url: str, db_path) -> tuple[int, int]:
    from .agent.compare import compare_runs
    from .agent.service import RunRequest, execute

    before = await execute(RunRequest(llm="mock", cassette="day3_checkout_flaws_on", flaws="on", checkout=True,
                                      paypal="mock"), store_url, db_path)
    after = await execute(RunRequest(llm="mock", cassette="day3_checkout_flaws_off", flaws="off", checkout=True,
                                     paypal="mock"), store_url, db_path)
    print(f"  {compare_runs(db_path, before, after)['headline']}")
    return before, after


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="python -m backend.app.seed", description="Set up the GhostShopper demo state")
    p.add_argument("--with-runs", action="store_true", help="record a before/after pair (mock LLM + mock PayPal)")
    a = p.parse_args(argv)
    settings = get_settings()
    db.init_db(settings.database_path)
    FlawStore(settings.database_path).set_many(bad_store_flaws())
    print(f"Database: {settings.database_path}")
    print(f"Store flaws set for the demo: ON = {', '.join(CLASSIC_FLAWS)}; all others off.")

    health = server_health(settings.app_base_url)
    if health is None:
        print(f"Server not reachable at {settings.app_base_url}; start it, then run the demo commands below.")
        if a.with_runs:
            print("--with-runs needs a running server.", file=sys.stderr)
            return 2
    else:
        print(f"Server: PAYPAL_MODE={health.get('paypal_mode')}, PayPal configured={health.get('paypal_configured')}, "
              f"Groq configured={health.get('groq_configured')}")
        if health.get("paypal_mode") == "mock":
            httpx.put(f"{settings.app_base_url}/mock-paypal/scenario", json={"scenario": "ok"}, timeout=5.0)
            print("Mock PayPal scenario reset to 'ok'.")
        if a.with_runs:
            if health.get("paypal_mode") != "mock":
                print("--with-runs only records against a PAYPAL_MODE=mock server (no live payments).", file=sys.stderr)
                return 2
            print("Recording a before/after pair (mock LLM, mock PayPal):")
            asyncio.run(record_before_after(f"{settings.app_base_url}/store/", settings.database_path))
            FlawStore(settings.database_path).set_many(bad_store_flaws())  # back to the bad store for the live demo
            print("Store reset to the bad state for the live demo.")

    pay = "sandbox" if (health or {}).get("paypal_mode", "sandbox") == "sandbox" else "mock"
    llm = "--llm groq" if (health or {}).get("groq_configured") else "--llm mock --cassette day3_checkout_flaws_on"
    llm_after = "--llm groq" if (health or {}).get("groq_configured") else "--llm mock --cassette day3_checkout_flaws_off"
    print("\nDemo commands:")
    print(f"  1. Bad store run:   python -m backend.app.agent {llm} --flaws keep --checkout --paypal {pay} --headed")
    print(f"  2. Apply fixes:     open {settings.app_base_url}/store/admin and untick everything (or --flaws off)")
    print(f"  3. Rerun:           python -m backend.app.agent {llm_after} --flaws off --checkout --paypal {pay} --headed")
    print("  4. Before/after:    python -m backend.app.agent.compare --last")
    return 0


if __name__ == "__main__":
    sys.exit(main())
