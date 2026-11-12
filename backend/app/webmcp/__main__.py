"""WebMCP test mode from the command line.

    python -m backend.app.webmcp discover https://webmcp-store.paypal.com/merchants/gift-cards?sdk=v6
    python -m backend.app.webmcp run --store demo --llm scripted --paypal mock          (against a PAYPAL_MODE=mock server)
    python -m backend.app.webmcp run --store showcase --llm live --paypal sandbox --headed
    python -m backend.app.webmcp compare --last
"""

import argparse
import asyncio
import json
import sys
from typing import Any

from ..agent.__main__ import print_awaiting_human
from ..agent.browser import BrowserSession, resolve_provider
from ..agent.loop import DEFAULT_TARGET
from ..agent.recorder import load_run
from ..agent.service import RunConfigError, RunRequest, execute
from ..agent.site import SiteError, allow_private_hosts, check_host, is_demo_store
from ..config import get_settings
from ..runs import purchase_trace
from .compare import PathCompareError, compare_paths, latest_pair
from .discover import LAUNCH_ARGS, Tools, install_shim
from .service import SHOWCASE_TARGET


def print_discovery(found: dict[str, Any]) -> None:
    print(f"Page: {found['url']}")
    print(f"Tool API: {found['source'] or 'no recorder (the page was not loaded with the shim)'}")
    print(f"PayPal web-sdk v6 script on the page: {found['paypal_sdk_v6']}; WebMCP script on the page: {found['webmcp_script']}")
    if found["context"]:
        print(f"Page context: {json.dumps(found['context'])}")
    print(f"{len(found['tools'])} tool(s):")
    for tool in found["tools"]:
        props = ", ".join((tool["input_schema"].get("properties") or {}))
        print(f"  {tool['name']}{' (read-only)' if tool['read_only'] else ''}({props})")
        if tool["description"]:
            print(f"      {tool['description']}")


async def discover_url(url: str, headed: bool, browser: str | None) -> dict[str, Any]:
    await check_host(url, allow_private_hosts(get_settings().app_base_url))
    async with BrowserSession(headless=not headed, provider=resolve_provider(browser), launch_args=LAUNCH_ARGS) as session:
        await install_shim(session.context)  # fallback only: native WebMCP is used when the browser has it
        tools = Tools(session.page)
        await tools.start()
        await session.page.goto(url, wait_until="load", timeout=30_000)
        return await tools.discover()


def print_run(run: dict[str, Any]) -> None:
    print(f"Run {run['id']}: path=webmcp status={run['status']} outcome={run['outcome']} end={run['end_reason']} "
          f"steps={run['step_count']} browser={run['browser']}")
    report = run.get("webmcp") or {}
    found = report.get("discovery") or {}
    print(f"  tools: {', '.join(t['name'] for t in found.get('tools', [])) or 'none'} (source: {found.get('source')})")
    for step in run["steps"]:
        print(f"  {step['idx']:>2} {'ok ' if step['ok'] else 'ERR'} {step['tool']:<28} {(step['observation'] or '')[:110]!r}")
    hand = report.get("handoff")
    if hand:
        problem = f" ({hand['problem']})" if hand.get("problem") else ""
        print(f"  hand-off: approval at {hand.get('approval_url_host')}, cart {hand.get('cart_id')}, approved={hand.get('approved')} "
              f"by {hand.get('approved_by')}{problem}")
    prices = report.get("price_consistency") or {}
    print(f"  unit prices {prices.get('unit_prices')}: consistent={prices.get('consistent')}")
    if report.get("label"):
        print(f"  {report['label']}")
    trace = run.get("trace") or {}
    first = trace.get("first_mismatch")
    print(f"  trace: {trace.get('counts')}" + (f"; first mismatch at {first['stage']} {first['field']}: {first['actual']}" if first else ""))
    if run["error"]:
        print("  error:", run["error"])


def main() -> int:
    p = argparse.ArgumentParser(prog="python -m backend.app.webmcp", description="GhostShopper WebMCP test mode")
    sub = p.add_subparsers(dest="command", required=True)
    d = sub.add_parser("discover", help="list the WebMCP tools a page registers (reads only)")
    d.add_argument("url")
    d.add_argument("--headed", action="store_true")
    d.add_argument("--browser", choices=["local", "kernel"])
    r = sub.add_parser("run", help="shop through the page's WebMCP tools and pay with PayPal")
    r.add_argument("--store", choices=["demo", "showcase"], default="demo",
                   help="demo = Fernhill (any PayPal mode); showcase = PayPal's own WebMCP demo store (sandbox only)")
    r.add_argument("--target", help=f"what to buy (default: {DEFAULT_TARGET!r}; {SHOWCASE_TARGET!r} on the showcase)")
    r.add_argument("--llm", choices=["live", "mock", "scripted"], default="live")
    r.add_argument("--cassette", help="mock: name of the recorded responses to replay (default webmcp_demo)")
    r.add_argument("--record", help="live: save this run's LLM replies as a cassette with this name")
    r.add_argument("--paypal", choices=["mock", "sandbox"], default="sandbox", help="must match the server's PAYPAL_MODE on the demo store")
    r.add_argument("--headed", action="store_true", help="show the browser window (needed for human approval locally)")
    r.add_argument("--flaws", default="keep", help="demo store: on, off, all, keep, or a comma-separated list of flaw keys")
    r.add_argument("--browser", choices=["local", "kernel"])
    r.add_argument("--max-steps", type=int, default=12)
    r.add_argument("--store-url", help="demo store: default APP_BASE_URL + /store/")
    c = sub.add_parser("compare", help="browser agent vs WebMCP on the same store")
    c.add_argument("browser_run", nargs="?", type=int)
    c.add_argument("webmcp_run", nargs="?", type=int)
    c.add_argument("--last", action="store_true", help="the latest run of each path on the same store")
    a = p.parse_args()
    settings = get_settings()

    if a.command == "discover":
        try:
            print_discovery(asyncio.run(discover_url(a.url, a.headed, a.browser)))
        except SiteError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 2
        return 0

    if a.command == "compare":
        try:
            ids = latest_pair(settings.database_path) if a.last or a.browser_run is None else (a.browser_run, a.webmcp_run)
            if ids[1] is None:
                raise PathCompareError("Give a browser run id and a WebMCP run id, or --last")
            runs = []
            for run_id in ids:
                run = load_run(settings.database_path, run_id)
                if run is None:
                    raise PathCompareError(f"No run {run_id}")
                runs.append({**run, "trace": purchase_trace(settings.database_path, run)})
            result = compare_paths(*runs)
        except PathCompareError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 2
        print(f"Run {ids[0]} (browser) vs run {ids[1]} (WebMCP): {result['verdict']}")
        for warning in result["warnings"]:
            print(f"  WARNING: {warning}")
        for path in ("browser", "webmcp"):
            side = result[path]
            print(f"  {path}: outcome={side['outcome']} steps={side['steps']} agent_steps={side['agent_steps']} llm_turns={side['llm_turns']} "
                  f"duration_s={side['duration_s']} handoff={side['handoff']} score={side['score']}")
            print(f"      tools: {side['tool_calls']}; bought {side['product']['bought']} for {side['price']['captured']} "
                  f"(catalog {side['price']['catalog']}); links ok {side['final']['links_ok']}/{side['final']['links_total']}; "
                  f"store order {side['final']['store_order_status']}")
        return 0

    external = a.store == "showcase"
    store_url = a.store_url or f"{settings.app_base_url}/store/"
    if not external and not is_demo_store(store_url, settings.app_base_url):
        print("Config error: purchases only run on the GhostShopper demo store or PayPal's WebMCP showcase.", file=sys.stderr)
        return 2
    req = RunRequest(llm=a.llm, cassette=a.cassette, record=a.record, flaws=a.flaws, checkout=True, paypal=a.paypal,
                     max_steps=a.max_steps, headless=not a.headed, browser=a.browser, path="webmcp",
                     store="paypal_showcase" if external else "demo",
                     target_product=a.target or (SHOWCASE_TARGET if external else DEFAULT_TARGET))

    async def go() -> int:
        from ..agent.service import resolve_target

        target = await resolve_target(req, settings.app_base_url)
        return await execute(req, target.url if external else store_url, settings.database_path,
                             on_awaiting_human=print_awaiting_human, live=False,
                             allow_private=allow_private_hosts(settings.app_base_url))

    try:
        run_id = asyncio.run(go())
    except RunConfigError as exc:
        print(f"Config error: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("Interrupted: the run was stopped and its browser session closed.", file=sys.stderr)
        return 130
    run = load_run(settings.database_path, run_id)
    print_run({**run, "trace": purchase_trace(settings.database_path, run)})
    return 0 if run["status"] == "completed" else 1


if __name__ == "__main__":
    sys.exit(main())
