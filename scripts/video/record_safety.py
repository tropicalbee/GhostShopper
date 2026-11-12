"""Record one live check with the hidden-instructions flaw on, for the demo video's safety beat.

The demo store hides a line aimed at AI agents in a product review. This starts one check from the recording browser,
waits for it, then shows the results page's "Instructions aimed at AI shoppers" panel. The store's flaws are put back
the way they were afterwards. Assumes a dev server is running.

    python scripts/video/record_safety.py --mode live --out demo-video/v2-safety
"""

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path

import httpx
from playwright.async_api import async_playwright

sys.path.insert(0, str(Path(__file__).resolve().parent))

from record_demo import HIDE_SCROLLBARS, SCALE, VIEW, Director, Screencast, set_store_flaws  # noqa: E402
from store.flaws import FLAW_KEYS  # noqa: E402

FLAW = "hidden_agent_instructions"


async def record(args) -> Path:
    base, out = args.base_url.rstrip("/"), Path(args.out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    httpx.get(f"{base}/api/health", timeout=10).raise_for_status()
    before = httpx.get(f"{base}/store/admin/flaws.json", timeout=10).json()
    set_store_flaws(base, {k: k == FLAW for k in FLAW_KEYS})
    try:
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=True)
            ctx = await browser.new_context(viewport=VIEW, device_scale_factor=SCALE)
            await ctx.add_init_script(HIDE_SCROLLBARS)
            page = await ctx.new_page()
            cast = Screencast(page, out.parent / f"{out.name}-frames" / time.strftime("%Y%m%d-%H%M%S"))
            d = Director(page, base)
            await d.goto("/")
            await cast.start()
            d.t0 = time.time()

            d.begin("safety_run_live")
            live = args.mode == "live"  # the same payload record_demo.py sends
            payload = {"llm": "live" if live else "mock", "paypal": "sandbox" if live else "mock", "checkout": True,
                       "browser": "local", "headed": live, "flaws": "keep",
                       **({"payment": "vault"} if live else {"cassette": "day3_checkout_flaws_off"})}
            run_id = await d.start_run(payload)
            await d.route(f"/run/{run_id}")
            await d.wait_done(run_id)
            d.end()

            d.begin("safety_results")
            await d.route(f"/run/{run_id}")
            await page.reload(wait_until="load")
            await page.wait_for_selector("#safety-h", timeout=30000)
            await asyncio.sleep(2)
            await d.scroll_to("#safety-h", 2.5, offset=120)
            await asyncio.sleep(1)
            await d.focus("panel", "section[aria-labelledby=safety-h]")
            await asyncio.sleep(10)
            d.end()

            await cast.stop()
            t_end = time.time()
            await ctx.close()
            await browser.close()
    finally:
        set_store_flaws(base, before)

    final = out / "raw-safety.mp4"
    print(f"Encoding {len(cast.frames)} frames", flush=True)
    cast.encode(d.t0, t_end, final)
    (out / "markers.json").write_text(json.dumps(
        {"video": str(final), "base_url": base, "mode": args.mode, "run": run_id, "viewport": VIEW,
         "scenes": d.markers, "focus": d.focus_marks}, indent=2))
    return final


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--base-url", default="http://localhost:8000")
    p.add_argument("--mode", choices=["mock", "live"], default="live")
    p.add_argument("--out", default="demo-video/v2-safety")
    print(f"Recorded {asyncio.run(record(p.parse_args()))}")


if __name__ == "__main__":
    main()
