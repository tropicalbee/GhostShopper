"""Record a read-only tour of the whole product for the demo video's montage.

Same screencast and markers format as record_demo.py, but it never starts a run or changes a flaw: the landing page
scrolled through every section, the New check page, and the demo store. Assumes a server is running.

    python scripts/video/record_tour.py --out demo-video/v2-tour
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

from record_demo import HIDE_SCROLLBARS, SCALE, VIEW, Director, Screencast  # noqa: E402


async def scroll_by(page, pixels: float, secs: float):
    """Ease the page down (or up) by `pixels` over `secs`."""
    await page.evaluate(
        """([dy, ms]) => new Promise(done => { const from = window.scrollY, t0 = performance.now();
          const step = now => { const k = Math.min(1, (now - t0) / ms), e = k < .5 ? 2*k*k : 1 - Math.pow(-2*k + 2, 2) / 2;
            window.scrollTo(0, from + dy * e); k < 1 ? requestAnimationFrame(step) : done(); };
          requestAnimationFrame(step); })""",
        [pixels, int(secs * 1000)])


async def record(args) -> Path:
    base, out = args.base_url.rstrip("/"), Path(args.out).resolve()  # ffmpeg's concat list needs absolute paths
    out.mkdir(parents=True, exist_ok=True)
    httpx.get(f"{base}/api/health", timeout=10).raise_for_status()

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        ctx = await browser.new_context(viewport=VIEW, device_scale_factor=SCALE)
        await ctx.add_init_script(HIDE_SCROLLBARS)
        page = await ctx.new_page()
        cast = Screencast(page, out.parent / f"{out.name}-frames" / time.strftime("%Y%m%d-%H%M%S"))
        d = Director(page, base)
        await page.goto(base + "/", wait_until="networkidle")  # warm up before the first frame
        await cast.start()
        d.t0 = time.time()

        d.begin("landing_hero")
        await asyncio.sleep(1)
        await d.focus("headline", "h1")
        await asyncio.sleep(d.left(5))
        d.end()

        # The rest of the landing page, one section at a time, with a pause on each.
        d.begin("landing_sections")
        for sel, hold in (("#how", 4.5), ("#trace", 5.0), ("#score", 6.0)):
            await d.scroll_to(sel, 2.2, offset=40)
            await asyncio.sleep(0.6)
            await d.focus(sel.strip("#"), sel)
            await asyncio.sleep(hold)
        await scroll_by(page, 1080 * 0.9, 2.2)  # "What it catches"
        await asyncio.sleep(0.6)
        await d.focus("catches", "section:nth-last-of-type(2)")
        await asyncio.sleep(5)
        await scroll_by(page, 1080, 2.0)  # the closing call to action and the footer
        await asyncio.sleep(3)
        d.end()

        d.begin("new_check")
        await d.route("/new")
        await page.wait_for_selector("text=Start check", timeout=30000)
        await asyncio.sleep(3)
        await d.focus("form", "main")
        await scroll_by(page, 700, 2.5)  # the store problems toggles
        await asyncio.sleep(3.5)
        await scroll_by(page, 700, 2.5)
        await asyncio.sleep(3)
        d.end()

        d.begin("store_home")
        await d.goto("/store/")
        await asyncio.sleep(3)
        await scroll_by(page, 900, 2.5)
        await asyncio.sleep(2.5)
        d.end()

        await cast.stop()
        t_end = time.time()
        await ctx.close()
        await browser.close()

    final = out / "raw-tour.mp4"
    print(f"Encoding {len(cast.frames)} frames", flush=True)
    cast.encode(d.t0, t_end, final)
    (out / "markers.json").write_text(json.dumps(
        {"video": str(final), "base_url": base, "mode": "tour", "viewport": VIEW,
         "scenes": d.markers, "focus": d.focus_marks}, indent=2))
    return final


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--base-url", default="http://localhost:8000")
    p.add_argument("--out", default="demo-video/v2-tour")
    print(f"Recorded {asyncio.run(record(p.parse_args()))}")


if __name__ == "__main__":
    main()
