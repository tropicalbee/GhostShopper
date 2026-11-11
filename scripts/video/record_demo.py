"""Record the GhostShopper demo as one raw video plus a markers.json that says where each scene sits.

Assumes a server is already running (default http://localhost:8000, a dev server). Starts nothing itself.

    python scripts/video/record_demo.py --mode mock --out demo-video/dry-run
    python scripts/video/record_demo.py --mode live --out demo-video/live

Frames come from a CDP screencast at 1.5x pixel density (Playwright's own video is 1 Mbps VP8 and too soft to zoom
into). markers.json also holds `focus` boxes, the on-screen spots the video zooms into (fractions of the viewport).
"""

import argparse
import asyncio
import base64
import json
import subprocess
import sys
import time
from pathlib import Path

import httpx
from playwright.async_api import Page, async_playwright

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from store.flaws import AGENT_FLAWS, CLASSIC_FLAWS, FLAW_KEYS  # noqa: E402

PRODUCT = "/store/products/speckled-stoneware-mug"
HOSTED_URL = "https://ghostshopper.onrender.com"
GITHUB_URL = "https://github.com/tropicalbee/GhostShopper"
VIEW = {"width": 1920, "height": 1080}
SCALE = 1.5  # device pixels per CSS pixel, so a 1.5x zoom stays sharp
HIDE_SCROLLBARS = """
(() => {
  const css = '*::-webkit-scrollbar{display:none!important} html,body{scrollbar-width:none!important}';
  const add = () => { const s = document.createElement('style'); s.textContent = css; (document.head || document.documentElement).appendChild(s); };
  if (document.head) add(); else document.addEventListener('DOMContentLoaded', add);
})();
"""
CLOSE_CARD = f"""<!doctype html><html><body style="margin:0;height:100vh;background:#000;color:#fff;display:flex;
flex-direction:column;align-items:center;justify-content:center;gap:36px;font-family:Arial,sans-serif">
<div style="font-size:72px;font-weight:700;letter-spacing:-1px">GhostShopper</div>
<div style="font-size:44px">{HOSTED_URL}</div>
<div style="font-size:44px;color:#bbb">{GITHUB_URL}</div></body></html>"""


class Screencast:
    """Saves every screencast frame as a JPEG with its wall-clock time, then joins them into a 30 fps mp4."""

    def __init__(self, page: Page, folder: Path):
        self.page, self.folder = page, folder
        self.frames: list[tuple[float, Path]] = []
        self.cdp = None

    async def start(self):
        self.folder.mkdir(parents=True, exist_ok=True)
        self.cdp = await self.page.context.new_cdp_session(self.page)
        self.cdp.on("Page.screencastFrame", self._on_frame)
        await self.cdp.send("Page.startScreencast", {
            "format": "jpeg", "quality": 92, "everyNthFrame": 1,
            "maxWidth": int(VIEW["width"] * SCALE), "maxHeight": int(VIEW["height"] * SCALE)})

    def _on_frame(self, params: dict):
        path = self.folder / f"{len(self.frames):06d}.jpg"
        path.write_bytes(base64.b64decode(params["data"]))
        self.frames.append((params["metadata"]["timestamp"], path))
        asyncio.ensure_future(self.cdp.send("Page.screencastFrameAck", {"sessionId": params["sessionId"]}))

    async def stop(self):
        await self.cdp.send("Page.stopScreencast")
        await asyncio.sleep(0.3)  # let the last frames land

    def encode(self, t0: float, t_end: float, out: Path):
        """Each frame stays on screen until the next one; the first one also covers the time from t0."""
        if not self.frames:
            raise RuntimeError("the screencast produced no frames")
        frames = sorted(self.frames)
        lines = []
        for k, (ts, path) in enumerate(frames):
            start = t0 if k == 0 else ts
            nxt = frames[k + 1][0] if k + 1 < len(frames) else t_end
            lines += [f"file '{path.as_posix()}'", f"duration {max(0.001, nxt - start):.4f}"]
        lines.append(f"file '{frames[-1][1].as_posix()}'")
        listing = self.folder / "frames.txt"
        listing.write_text("\n".join(lines) + "\n", encoding="utf-8")
        w, h = int(VIEW["width"] * SCALE), int(VIEW["height"] * SCALE)
        r = subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", str(listing),
                            "-vf", f"fps=30,scale={w}:{h}:flags=lanczos,format=yuv420p", "-c:v", "libx264",
                            "-preset", "fast", "-crf", "16", "-g", "30", "-movflags", "+faststart", str(out)],
                           capture_output=True, text=True)
        if r.returncode != 0:
            raise RuntimeError(f"ffmpeg could not encode the frames:\n{r.stderr[-1500:]}")


class Director:
    def __init__(self, page: Page, base: str):
        self.page, self.base = page, base.rstrip("/")
        self.t0 = time.time()  # wall clock, the same clock as the screencast frame timestamps
        self.markers: list[dict] = []
        self.focus_marks: list[dict] = []
        self._open: dict | None = None

    def now(self) -> float:
        return round(time.time() - self.t0, 2)

    async def focus(self, name: str, selector: str):
        """Note where an element sits right now, so the video can zoom into it."""
        box = await self.page.evaluate(
            """s => { const el = document.querySelector(s); if (!el) return null; const r = el.getBoundingClientRect();
              return [r.left / innerWidth, r.top / innerHeight, r.width / innerWidth, r.height / innerHeight]; }""",
            selector)
        if box is None:
            print(f"  WARNING focus {name}: nothing matches {selector}", flush=True)
            return
        self.focus_marks.append({"name": f"{self._open['scene']}.{name}", "t": self.now(),
                                 "box": [round(v, 4) for v in box]})

    def begin(self, name: str):
        self._open = {"scene": name, "start": self.now()}
        print(f"  scene {name} @ {self._open['start']}s", flush=True)

    def end(self):
        self._open["end"] = self.now()
        self.markers.append(self._open)
        self._open = None

    def left(self, target: float) -> float:
        """Seconds still to wait so the open scene lasts `target` seconds (at least a beat)."""
        return max(1.0, target - (self.now() - self._open["start"]))

    async def goto(self, path: str):
        await self.page.goto(self.base + path, wait_until="load")

    async def route(self, hash_path: str):
        """Change the SPA route without reloading."""
        await self.page.evaluate("h => { window.location.hash = h }", hash_path)

    async def scroll_to(self, selector: str, secs: float, offset: int = 90):
        await self.page.evaluate(
            """([sel, ms, off]) => new Promise(done => {
              const el = document.querySelector(sel); if (!el) return done(false);
              const from = window.scrollY, to = Math.max(0, el.getBoundingClientRect().top + from - off);
              const t0 = performance.now();
              const step = now => {
                const k = Math.min(1, (now - t0) / ms), e = k < .5 ? 2*k*k : 1 - Math.pow(-2*k + 2, 2) / 2;
                window.scrollTo(0, from + (to - from) * e);
                k < 1 ? requestAnimationFrame(step) : done(true);
              };
              requestAnimationFrame(step);
            })""",
            [selector, int(secs * 1000), offset],
        )

    async def scroll_top(self, secs: float = 1.0):
        await self.page.evaluate(
            """ms => new Promise(done => { const from = window.scrollY, t0 = performance.now();
              const step = now => { const k = Math.min(1, (now - t0) / ms); window.scrollTo(0, from * (1 - k));
                k < 1 ? requestAnimationFrame(step) : done(); }; requestAnimationFrame(step); })""",
            int(secs * 1000),
        )

    async def api(self, method: str, path: str, body: dict | None = None) -> dict:
        res = await self.page.evaluate(
            """async ([m, p, b]) => { const r = await fetch(p, {method: m, headers: {'content-type': 'application/json'},
              body: b ? JSON.stringify(b) : undefined}); let j = null; try { j = await r.json() } catch (e) {}
              return {ok: r.ok, status: r.status, json: j}; }""",
            [method, path, body],
        )
        if not res["ok"]:
            raise RuntimeError(f"{method} {path} failed with {res['status']}: {json.dumps(res['json'])[:300]}")
        return res["json"]

    async def start_run(self, payload: dict) -> int:
        out = await self.api("POST", "/api/runs", payload)
        print(f"  started run {out['run_id']}", flush=True)
        return out["run_id"]

    async def wait_done(self, run_id: int, timeout: float = 1500):  # a live run may wait up to 600 s for a human
        deadline = time.perf_counter() + timeout
        while time.perf_counter() < deadline:
            run = await self.api("GET", f"/api/runs/{run_id}")
            if run["status"] not in ("running", "awaiting_human"):
                print(f"  run {run_id} finished: {run['status']}", flush=True)
                return run
            await asyncio.sleep(1)
        raise TimeoutError(f"run {run_id} still running after {timeout}s")


def set_store_flaws(base: str, flaws: dict[str, bool]):
    r = httpx.put(f"{base}/store/admin/flaws.json", json={"flaws": flaws}, timeout=10)
    if r.status_code != 200:
        raise RuntimeError(f"could not set store flaws ({r.status_code}); is this a dev server with the admin open?")


async def record(args) -> Path:
    base = args.base_url.rstrip("/")
    out = Path(args.out).resolve()
    video_dir = out / "raw"
    video_dir.mkdir(parents=True, exist_ok=True)
    live = args.mode == "live"
    common = {"llm": "live" if live else "mock", "paypal": "sandbox" if live else "mock", "checkout": True,
              "browser": "local", "headed": live, "flaws": "keep", **({"payment": args.payment} if live else {})}

    def payload(cassette: str) -> dict:
        return {**common, **({} if live else {"cassette": cassette})}

    httpx.get(f"{base}/api/health", timeout=10).raise_for_status()
    # The bad store: classic flaws on, everything else off (what backend/app/seed.py sets).
    set_store_flaws(base, {k: k in CLASSIC_FLAWS for k in FLAW_KEYS})

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        ctx = await browser.new_context(viewport=VIEW, device_scale_factor=SCALE)
        await ctx.add_init_script(HIDE_SCROLLBARS)
        page = await ctx.new_page()
        # Frames go next to the take folder, not in it: Remotion copies the take folder into every render bundle.
        cast = Screencast(page, out.parent / f"{out.name}-frames" / time.strftime("%Y%m%d-%H%M%S"))
        d = Director(page, base)
        await cast.start()
        d.t0 = time.time()

        # (a) the store product page
        d.begin("store")
        await d.goto(PRODUCT)
        await d.focus("price", ".product-price")
        await d.focus("buttons", ".actions")
        await asyncio.sleep(d.left(args.store_hold))
        d.end()

        # (b) the landing page
        d.begin("landing")
        await d.goto("/")
        await asyncio.sleep(d.left(args.landing_hold))
        d.end()

        async def run_scene(name: str, cassette: str) -> int:
            """Start a run from this page (so it uses this browser's owner cookie) and show its live view."""
            d.begin(name)
            run_id = await d.start_run(payload(cassette))
            await d.goto(f"/#/run/{run_id}")
            try:
                await page.wait_for_selector("section[aria-label='What the browser sees']", timeout=15000)
                await d.focus("browser", "section[aria-label='What the browser sees']")
                await d.focus("feed", "ol[aria-label='What the shopper is doing']")
            except Exception as e:  # a very fast mock run can finish before the live view paints
                print(f"  WARNING no live view focus: {e}", flush=True)
            await d.wait_done(run_id)
            await asyncio.sleep(1.5)
            d.end()
            return run_id

        # (c) the bad-store run
        bad = await run_scene("bad_run_live", args.before_cassette)

        # (d) results of the bad run: score, the AG Grid failures table, then the fix list
        d.begin("bad_results")
        await d.route(f"/run/{bad}")
        await page.wait_for_selector("#fix-first", timeout=30000)
        await d.focus("summary", "[aria-label=Summary]")
        await asyncio.sleep(5)
        await d.route(f"/run/{bad}/advanced")
        await page.wait_for_selector("[role=tablist]", timeout=30000)
        await asyncio.sleep(3)
        await d.scroll_to("[role=tablist]", 3.5, offset=40)
        await page.wait_for_selector(".ag-row", timeout=30000)
        await asyncio.sleep(2)
        await page.locator(".ag-row[row-index='0']").last.hover(position={"x": 200, "y": 20}, timeout=10000)
        await asyncio.sleep(1)
        await d.focus("grid", ".ag-root-wrapper")
        await asyncio.sleep(d.left(args.bad_results))
        d.end()

        d.begin("bad_fixes")
        await d.route(f"/run/{bad}")
        await page.wait_for_selector("#fix-first", timeout=30000)
        await d.scroll_top(0.2)
        await asyncio.sleep(1.5)
        await d.scroll_to("#fix-first", 3.0, offset=80)
        await d.focus("fixes", "section[aria-labelledby=fix-first]")
        await asyncio.sleep(d.left(args.bad_fixes))
        d.end()

        # (e) the merchant applies the fixes in the store admin
        d.begin("admin")
        await d.goto("/store/admin")
        await d.focus("form", "form")
        await asyncio.sleep(2)
        for key in AGENT_FLAWS:
            box = page.locator(f"input[name={key}]")
            await box.scroll_into_view_if_needed()
            await box.uncheck()
            await asyncio.sleep(0.9)
        await asyncio.sleep(1)
        await page.get_by_role("button", name="Save settings").click()
        await page.wait_for_load_state("load")
        await asyncio.sleep(d.left(args.admin_hold))
        d.end()

        # (f) the fixed-store run
        await d.goto("/")
        fixed = await run_scene("fixed_run_live", args.after_cassette)

        # (g) results of the fixed run: purchase trace, compare view, market check
        d.begin("fixed_trace")
        await d.route(f"/run/{fixed}")
        await page.wait_for_selector("#trace-h", timeout=30000)
        await asyncio.sleep(2)
        await d.scroll_to("#trace-h", 3.0, offset=60)
        await d.focus("trace", "section[aria-labelledby=trace-h]")
        await d.focus("links", "section[aria-labelledby=linked-by-id]")
        await asyncio.sleep(d.left(args.trace_hold))
        d.end()

        d.begin("compare")
        await d.route(f"/run/{fixed}/compare")
        await page.wait_for_selector("h1", timeout=30000)
        await d.scroll_top(0.2)
        await asyncio.sleep(d.left(args.compare_hold))
        d.end()

        d.begin("market")
        await d.route(f"/run/{fixed}/advanced")
        tab = page.get_by_role("tab", name="Market")
        await tab.wait_for(timeout=30000)
        await tab.click()
        await d.scroll_to("[role=tablist]", 1.0, offset=40)
        await d.focus("panel", "[role=tabpanel]")
        await asyncio.sleep(d.left(args.market_hold))
        d.end()

        # (h) the closing card with the hosted URL and the repo
        d.begin("close")
        await page.set_content(CLOSE_CARD)
        await asyncio.sleep(d.left(args.close_hold))
        d.end()

        await cast.stop()
        t_end = time.time()
        await ctx.close()
        await browser.close()

    final = out / "raw-demo.mp4"
    print(f"Encoding {len(cast.frames)} frames", flush=True)
    cast.encode(d.t0, t_end, final)  # replaces our own output from an earlier take
    (out / "markers.json").write_text(json.dumps(
        {"video": str(final), "base_url": base, "mode": args.mode, "runs": {"bad": bad, "fixed": fixed},
         "viewport": VIEW, "scenes": d.markers, "focus": d.focus_marks}, indent=2))
    return final


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--base-url", default="http://localhost:8000")
    p.add_argument("--out", default=str(ROOT / "demo-video"))
    p.add_argument("--mode", choices=["mock", "live"], default="mock")
    p.add_argument("--payment", choices=["vault", "popup"], default="vault",
                   help="live mode: vault pays with the saved sandbox buyer (python -m backend.app.vault setup)")
    p.add_argument("--before-cassette", default="day3_checkout_flaws_on")
    p.add_argument("--after-cassette", default="day3_checkout_flaws_off")
    p.add_argument("--store-hold", type=float, default=8)
    p.add_argument("--landing-hold", type=float, default=8)
    p.add_argument("--bad-results", type=float, default=23)
    p.add_argument("--bad-fixes", type=float, default=10)
    p.add_argument("--admin-hold", type=float, default=11)
    p.add_argument("--trace-hold", type=float, default=25)
    p.add_argument("--compare-hold", type=float, default=7)
    p.add_argument("--market-hold", type=float, default=4)
    p.add_argument("--close-hold", type=float, default=10)
    args = p.parse_args()
    final = asyncio.run(record(args))
    print(f"Recorded {final}")


if __name__ == "__main__":
    main()
