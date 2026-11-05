"""Browser tools the shopper agent can call, on local Playwright.

Element ids (e1, e2, ...) are assigned in DOM order each time the page is inspected, so the same page
always yields the same ids. That keeps recorded LLM responses replayable.
"""

import os
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse

import httpx

# Browsers live inside the venv's playwright package (installed with PLAYWRIGHT_BROWSERS_PATH=0),
# not in the user profile. Must be set before Playwright starts its driver.
os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", "0")

from playwright.async_api import Browser, BrowserContext, Page, Playwright, async_playwright  # noqa: E402

from .site import USER_AGENT, Politeness, SiteError, check_host  # noqa: E402

FACTS_JS = r"""
() => {
  const SEMANTIC = 'a[href], button, input:not([type=hidden]), select, textarea, [role=button], [role=link], summary';
  const visible = (el) => {
    const s = getComputedStyle(el);
    if (s.display === 'none' || s.visibility === 'hidden' || el.hidden) return false;
    const r = el.getBoundingClientRect();
    return r.width > 0 && r.height > 0;
  };
  const cssPath = (el) => {
    const parts = [];
    while (el && el.nodeType === 1 && parts.length < 4) {
      if (el.id) { parts.unshift('#' + CSS.escape(el.id)); break; }
      let p = el.tagName.toLowerCase();
      if (el.classList.length) p += '.' + [...el.classList].map(c => CSS.escape(c)).join('.');
      else if (el.parentElement) {
        const sibs = [...el.parentElement.children].filter(c => c.tagName === el.tagName);
        if (sibs.length > 1) p += ':nth-of-type(' + (sibs.indexOf(el) + 1) + ')';
      }
      parts.unshift(p);
      el = el.parentElement;
    }
    return parts.join(' > ');
  };
  const clean = (s) => (s || '').trim().replace(/\s+/g, ' ').slice(0, 80);
  const labelText = (el) => {
    const lab = el.labels && el.labels[0];
    if (!lab) return '';
    return clean([...lab.childNodes].filter(n => n.nodeType === 3).map(n => n.textContent).join(' '));
  };
  const name = (el) => {
    const isBtnInput = el.tagName === 'INPUT' && ['submit', 'button'].includes(el.type);
    const img = el.querySelector('img[alt]');
    const custom = el.tagName.includes('-');  // web components (e.g. <paypal-button>) render text in shadow DOM
    const tries = [el.getAttribute('aria-label'), labelText(el), el.tagName === 'SELECT' ? '' : el.innerText,
                   custom && el.shadowRoot ? el.shadowRoot.textContent : '',
                   el.getAttribute('alt'), img && img.getAttribute('alt'), el.getAttribute('title'), el.getAttribute('placeholder'),
                   isBtnInput ? el.value : '', el.getAttribute('name'),
                   custom ? el.tagName.toLowerCase().replace(/-/g, ' ') : ''];
    for (const t of tries) if (clean(t)) return clean(t);
    return '';
  };

  document.querySelectorAll('[data-gs-id]').forEach(e => e.removeAttribute('data-gs-id'));
  const controls = [];
  let n = 0;
  for (const el of document.body.querySelectorAll('*')) {
    const tag = el.tagName.toLowerCase();
    const semantic = el.matches(SEMANTIC);
    const customButton = tag.includes('-') && tag.endsWith('-button');
    const handler = !semantic && !customButton && (el.hasAttribute('onclick') ||
      (getComputedStyle(el).cursor === 'pointer' && !(el.parentElement && el.parentElement.closest('[onclick]'))));
    if (!(semantic || customButton || handler)) continue;
    const outer = el.parentElement && el.parentElement.closest(SEMANTIC);
    if (outer) continue;
    if (!visible(el)) continue;
    const id = 'e' + (++n);
    el.setAttribute('data-gs-id', id);
    const c = { id, tag, selector: cssPath(el), text: name(el), semantic: semantic || customButton,
                in_main: !!el.closest('main') };
    if (tag === 'a') c.href = el.getAttribute('href');
    if (tag === 'input') {
      c.type = el.type;
      if (['checkbox', 'radio'].includes(el.type)) c.checked = el.checked;
      else if (el.type !== 'password') c.value = el.value;  // never echo password fields
    }
    if (tag === 'select') { c.options = [...el.options].map(o => o.text.trim()); c.value = el.value; }
    if (el.required) c.required = true;
    controls.push(c);
  }
  const main = document.querySelector('main') || document.body;
  // Is each control in <main> covered by something else? Hit-test its center, then restore the scroll.
  const sx = window.scrollX, sy = window.scrollY;
  for (const c of controls) {
    if (!c.in_main) continue;
    const el = document.querySelector('[data-gs-id="' + c.id + '"]');
    el.scrollIntoView({ block: 'center', inline: 'center' });
    const r = el.getBoundingClientRect();
    const top = document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2);
    c.covered = !!top && top !== el && !el.contains(top) && !top.contains(el);
    if (c.covered) c.covered_by = cssPath(top);
  }
  window.scrollTo(sx, sy);

  // Prices as text in <main>; struck-through "was" prices are collected separately.
  const STRUCK = 's, del, strike, [class*="was"], [class*="compare"], [class*="old-price"]';
  const CUR = /(?:US\$|\$|USD\s?|€|£)\s?(\d{1,3}(?:,\d{3})*(?:\.\d{2})?)/;
  const BARE = /^(\d{1,4}\.\d{2})$/;
  const prices = [], struck_prices = [];
  const walker = document.createTreeWalker(main, NodeFilter.SHOW_TEXT);
  for (let node = walker.nextNode(); node; node = walker.nextNode()) {
    const t = node.textContent.trim();
    if (!t || !node.parentElement || !visible(node.parentElement)) continue;
    const m = t.match(CUR), b = t.match(BARE);
    if (!m && !b) continue;
    const entry = { text: t.slice(0, 40), value: (m ? m[1] : b[1]).replace(/,/g, ''), currency: !!m,
                    selector: cssPath(node.parentElement) };
    (node.parentElement.closest(STRUCK) ? struck_prices : prices).push(entry);
  }
  const pct = (main.innerText.match(/(\d{1,2})\s?%\s*off/i) || [])[1];
  const images = [...main.querySelectorAll('img')]
    .filter(i => visible(i) && i.getBoundingClientRect().width >= 150)
    .map(i => ({ selector: cssPath(i), alt: i.getAttribute('alt'), src: i.getAttribute('src') }));
  const jsonld = [...document.querySelectorAll('script[type="application/ld+json"]')].map(s => {
    try { return JSON.parse(s.textContent); } catch (e) { return { _parse_error: String(e) }; }
  });
  const images_without_alt = [...main.querySelectorAll('img')]
    .filter(i => !(i.getAttribute('alt') || '').trim() && visible(i))
    .map(i => ({ selector: cssPath(i), src: i.getAttribute('src') }));
  const forms = [...document.querySelectorAll('form')].map(f => ({
    selector: cssPath(f),
    fields: [...f.querySelectorAll('input:not([type=hidden]), select, textarea')].map(name),
  }));
  const PAYPAL_SEL = 'paypal-button, iframe[src*="paypal.com"], iframe[title*="PayPal" i], [data-funding-source="paypal"], ' +
                     '.paypal-buttons, #paypal-button-container, [id*="paypal-button" i], [aria-label*="PayPal" i]';
  const BOT_RE = /just a moment|checking your browser|verify (that )?you are (a )?human|verify you're human|attention required|are you a robot|ddos protection|security check to access|please complete the security check/i;
  const head = document.title + ' ' + (document.body ? document.body.innerText.slice(0, 3000) : '');
  const meta = (sel) => { const m = document.querySelector(sel); return m ? m.getAttribute('content') : null; };
  return {
    url: location.href,
    title: document.title,
    main_text: main.innerText.slice(0, 6000),
    jsonld, controls, images_without_alt, forms, prices, struck_prices, images,
    sale_percent: pct ? Number(pct) : null,
    has_payment_button: !!document.querySelector(PAYPAL_SEL),
    og_type: meta('meta[property="og:type"]'),
    bot_check: BOT_RE.test(head) || !!document.querySelector(
      '#challenge-form, .cf-browser-verification, #cf-challenge-running, iframe[src*="challenges.cloudflare.com"], .g-recaptcha, .h-captcha'),
    platform_signals: {
      generator: meta('meta[name="generator"]'),
      scripts: [...document.scripts].map(s => s.src).filter(Boolean).slice(0, 60),
      links: [...document.querySelectorAll('link[href]')].map(l => l.href).slice(0, 40),
      body_class: document.body ? document.body.className : '',
      globals: ['Shopify', 'wixBiSession', 'woocommerce_params', 'wc_add_to_cart_params'].filter(k => k in window),
    },
  };
}
"""

# Live stores: is there a PayPal button, is it visible, and would a click land on it? Never clicks.
PAYPAL_CHECK_JS = r"""
() => {
  const SEL = 'paypal-button, iframe[src*="paypal.com"], iframe[title*="PayPal" i], [data-funding-source="paypal"], ' +
              '.paypal-buttons, #paypal-button-container, [id*="paypal-button" i], [aria-label*="PayPal" i]';
  const path = (el) => { const p = []; while (el && el.nodeType === 1 && p.length < 4) { let s = el.tagName.toLowerCase();
    if (el.id) { p.unshift('#' + el.id); break; } if (el.classList.length) s += '.' + [...el.classList].slice(0, 2).join('.');
    p.unshift(s); el = el.parentElement; } return p.join(' > '); };
  const found = [...document.querySelectorAll(SEL)];
  if (!found.length) return { found: false };
  let best = null;
  for (const el of found) {
    const s = getComputedStyle(el), r = el.getBoundingClientRect();
    const visible = !el.hidden && s.display !== 'none' && s.visibility !== 'hidden' && Number(s.opacity) > 0.05 && r.width >= 20 && r.height >= 14;
    const info = { found: true, visible, selector: path(el), clickable: false, covered_by: null,
                   disabled: el.disabled === true || el.getAttribute('aria-disabled') === 'true' };
    if (visible) {
      el.scrollIntoView({ block: 'center' });
      const r2 = el.getBoundingClientRect();
      const top = document.elementFromPoint(r2.left + r2.width / 2, r2.top + r2.height / 2);
      info.clickable = !info.disabled && !!top && (top === el || el.contains(top) || top.contains(el));
      if (top && !info.clickable && !info.disabled) info.covered_by = path(top);
    }
    if (!best || (info.visible && !best.visible) || (info.clickable && !best.clickable)) best = info;
    if (best.clickable) break;
  }
  return best;
}
"""


PROVIDERS = ("local", "kernel")
KERNEL_API_BASE = "https://api.onkernel.com"
VIEWPORT = {"width": 1280, "height": 900}


class BrowserConfigError(ValueError):
    pass


def resolve_provider(name: str | None = None) -> str:
    """local (default) or kernel. Kernel only when explicitly chosen and KERNEL_API_KEY is set."""
    provider = (name or os.getenv("BROWSER_PROVIDER") or "local").strip().lower()
    if provider not in PROVIDERS:
        raise BrowserConfigError(f"Browser provider must be one of {PROVIDERS}, got {provider!r}")
    if provider == "kernel" and not os.getenv("KERNEL_API_KEY", "").strip():
        raise BrowserConfigError("Browser provider 'kernel' needs KERNEL_API_KEY in .env (or use 'local').")
    return provider


class KernelBrowsers:
    """Kernel's REST API for browser sessions (https://www.kernel.sh/docs). Same calls as the `kernel` SDK."""

    def __init__(self, api_key: str, http: httpx.AsyncClient | None = None):
        self._http = http or httpx.AsyncClient(
            base_url=KERNEL_API_BASE, timeout=60.0, headers={"Authorization": f"Bearer {api_key}"})

    async def create(self, *, headless: bool, timeout_seconds: int) -> dict[str, Any]:
        # stealth stays off: it enables Kernel's CAPTCHA solver, and we never bypass PayPal's checks.
        resp = await self._http.post("/browsers", json={
            "headless": headless, "stealth": False, "timeout_seconds": timeout_seconds,
            "viewport": {"width": VIEWPORT["width"], "height": VIEWPORT["height"]}})
        if resp.status_code not in (200, 201):
            raise RuntimeError(f"Kernel create browser failed: {resp.status_code} {resp.text[:200]}")
        return resp.json()

    async def delete(self, session_id: str) -> None:
        resp = await self._http.delete(f"/browsers/{session_id}")
        if resp.status_code not in (200, 204, 404):
            raise RuntimeError(f"Kernel delete browser failed: {resp.status_code} {resp.text[:200]}")

    async def aclose(self) -> None:
        await self._http.aclose()


class BrowserSession:
    """One browser + context + page for a run, from local Playwright or a Kernel cloud browser (over CDP).
    The agent code above this class is identical for both."""

    def __init__(self, headless: bool = True, provider: str | None = None,
                 kernel: KernelBrowsers | None = None, kernel_timeout_s: int = 900,
                 politeness: Politeness | None = None, allow_private: bool = True):
        self.headless = headless
        self.provider = resolve_provider(provider) if kernel is None else "kernel"
        self._kernel = kernel
        self._kernel_timeout_s = kernel_timeout_s
        self.session_id: str | None = None
        self.live_view_url: str | None = None  # Kernel, non-headless only: lets a human see/act in the browser
        # Live stores: robots.txt, rate limit and the public-host rule on every page load.
        self.politeness = politeness
        self.allow_private = allow_private
        self.refused: dict[str, str] = {}  # url -> why we didn't load it
        self._host_ok: dict[str, str | None] = {}  # host -> None if public, else why it's refused (per run)
        self._pw: Playwright | None = None
        self.browser: Browser | None = None
        self.context: BrowserContext | None = None
        self.page: Page | None = None

    async def __aenter__(self) -> "BrowserSession":
        self._pw = await async_playwright().start()
        try:
            if self.provider == "kernel":
                await self._open_kernel()
            else:
                channel = os.getenv("PLAYWRIGHT_CHANNEL") or None  # e.g. "msedge" to use the installed Edge
                self.browser = await self._pw.chromium.launch(headless=self.headless, channel=channel)
                extra = {"user_agent": USER_AGENT} if self.politeness else {}
                self.context = await self.browser.new_context(viewport=VIEWPORT, **extra)
                self.page = await self.context.new_page()
            if self.politeness:
                await self.context.route("**/*", self._guard)
        except BaseException:
            await self.__aexit__()
            raise
        return self

    async def _guard(self, route, request) -> None:
        """Live stores. Every request (pages, frames, images, scripts) must go to a public host, so a page
        can't make our browser load an internal address and show it in a screenshot. Main-frame page loads
        also follow robots.txt and a polite pace."""
        url = request.url
        if not url.startswith(("http://", "https://")):
            await route.continue_()  # data:, blob: and the like never leave the browser
            return
        frame = request.frame
        main_load = (request.resource_type == "document" and request.is_navigation_request()
                     and not (frame and frame.parent_frame is not None))
        host = urlparse(url).hostname or ""
        if host not in self._host_ok:
            try:
                await check_host(url, self.allow_private)
                self._host_ok[host] = None
            except SiteError as exc:
                self._host_ok[host] = str(exc)
        refusal = self._host_ok[host]
        if refusal:
            if main_load:
                self.refused[url] = refusal
            await route.abort("blockedbyclient")
            return
        if main_load and self.politeness:
            if not await self.politeness.allowed(url):
                self.refused[url] = "robots.txt asks automated visitors not to open this page"
                await route.abort("blockedbyclient")
                return
            await self.politeness.wait_turn(url)
        await route.continue_()

    async def _open_kernel(self) -> None:
        if self._kernel is None:
            self._kernel = KernelBrowsers(os.environ["KERNEL_API_KEY"].strip())
        info = await self._kernel.create(headless=self.headless, timeout_seconds=self._kernel_timeout_s)
        self.session_id = info["session_id"]
        self.live_view_url = info.get("browser_live_view_url")
        self.browser = await self._pw.chromium.connect_over_cdp(info["cdp_ws_url"])
        self.context = self.browser.contexts[0] if self.browser.contexts else await self.browser.new_context()
        self.page = self.context.pages[0] if self.context.pages else await self.context.new_page()
        await self.page.set_viewport_size(VIEWPORT)

    async def __aexit__(self, *exc) -> None:
        try:
            if self.provider == "local" and self.context:
                await self.context.close()
            if self.browser:
                await self.browser.close()  # for Kernel this only disconnects CDP
        finally:
            if self._kernel and self.session_id:
                await self._kernel.delete(self.session_id)
            if self._pw:
                await self._pw.stop()


def describe_controls(controls: list[dict[str, Any]], kind: str = "all") -> str:
    lines = []
    for c in controls:
        tag = c["tag"]
        if kind == "links" and tag != "a":
            continue
        if kind == "buttons" and not (tag == "button" or tag.endswith("-button") or not c["semantic"]
                                      or c.get("type") in ("submit", "button")):
            continue
        if kind == "inputs" and tag not in ("input", "select", "textarea"):
            continue
        if not c["semantic"]:
            kind_label = f"{tag} (clickable, not a real button)"
        elif tag == "input":
            kind_label = f"input[{c.get('type')}]"
        else:
            kind_label = tag
        line = f"{c['id']} {kind_label} '{c['text']}'"
        if c.get("href"):
            line += f" -> {c['href']}"
        if "checked" in c:
            line += f" checked={str(c['checked']).lower()}"
        if c.get("value"):
            line += f" value='{c['value']}'"
        if c.get("options"):
            line += " options: " + " | ".join(c["options"])
        if c.get("required"):
            line += " (required)"
        lines.append(line)
    return "\n".join(lines) if lines else "(no matching elements)"


def describe_text(facts: dict[str, Any], limit: int = 2500) -> str:
    blocks = facts.get("jsonld") or []
    if blocks:
        sd = "\n".join(str(b)[:600] for b in blocks)
    else:
        sd = "none"
    text = facts.get("main_text") or ""
    if len(text) > limit:
        text = text[:limit] + " ..."
    return f"Title: {facts.get('title')}\nURL: {facts.get('url')}\nMain text:\n{text}\nStructured data (JSON-LD): {sd}"


class ToolError(Exception):
    pass


class PageTools:
    """The generic browsing tools. Every method returns the observation text for the LLM."""

    def __init__(self, session: BrowserSession, store_url: str, shots_dir: Path):
        self.s = session
        self.store_url = store_url
        self._origin = urlparse(store_url).netloc
        self.shots_dir = shots_dir
        self._shot_n = 0

    @property
    def page(self) -> Page:
        assert self.s.page is not None
        return self.s.page

    async def facts(self) -> dict[str, Any]:
        return await self.page.evaluate(FACTS_JS)

    async def _settle(self) -> None:
        try:
            await self.page.wait_for_load_state("load", timeout=10_000)
        except Exception:
            pass

    async def _where(self) -> str:
        return f"Now on: {await self.page.title()} ({self.page.url})"

    async def open_page(self, url: str) -> str:
        target = urljoin(self.page.url if self.page.url.startswith("http") else self.store_url, url)
        if urlparse(target).netloc != self._origin:
            raise ToolError(f"Only pages on {self._origin} can be opened in this run.")
        try:
            resp = await self.page.goto(target, wait_until="load", timeout=20_000)
        except Exception as exc:
            why = self.s.refused.get(target)
            if why:
                raise ToolError(f"Not opened: {why}. Try another link.") from exc
            raise
        status = resp.status if resp else "unknown"
        return f"HTTP {status}. {await self._where()}"

    async def paypal_button_state(self) -> dict[str, Any]:
        return await self.page.evaluate(PAYPAL_CHECK_JS)

    async def find_elements(self, kind: str = "all") -> str:
        facts = await self.facts()
        return f"{await self._where()}\n{describe_controls(facts['controls'], kind)}"

    async def read_text(self) -> str:
        return describe_text(await self.facts())

    async def _locate(self, element_id: str):
        if not element_id or not element_id.startswith("e") or not element_id[1:].isdigit():
            raise ToolError(f"Bad element id {element_id!r}; use ids from find_elements.")
        loc = self.page.locator(f'[data-gs-id="{element_id}"]')
        if await loc.count() == 0:
            raise ToolError(f"Element {element_id} not found on this page; call find_elements again.")
        return loc.first

    async def is_payment_element(self, element_id: str) -> bool:
        """Our <paypal-button>, or anything on a live store that is or sits in a PayPal button."""
        loc = await self._locate(element_id)
        return await loc.evaluate(
            "el => /paypal/i.test([el.tagName, el.id, String(el.className), el.getAttribute('aria-label') || '',"
            " el.getAttribute('title') || '', (el.innerText || '').slice(0, 60)].join(' '))"
            " || !!el.closest('.paypal-buttons, #paypal-button-container, [data-funding-source=\"paypal\"]')")

    async def has_password_field(self, fields: list[dict[str, Any]]) -> bool:
        for f in fields or []:
            loc = await self._locate(f.get("element_id"))
            if await loc.evaluate("el => (el.type || '').toLowerCase() === 'password'"):
                return True
        return False

    async def element_tag(self, element_id: str) -> str:
        loc = await self._locate(element_id)
        return await loc.evaluate("el => el.tagName.toLowerCase()")

    async def click(self, element_id: str) -> str:
        loc = await self._locate(element_id)
        label = (await loc.inner_text(timeout=2_000)).strip()[:60] if await loc.count() else ""
        refused_before = len(self.s.refused)
        await loc.click(timeout=5_000)
        await self.page.wait_for_timeout(300)  # let onclick navigations start
        await self._settle()
        if len(self.s.refused) > refused_before:
            why = list(self.s.refused.values())[-1]
            raise ToolError(f"Clicked '{label}' but the page was not opened: {why}. Try another link.")
        return f"Clicked {element_id} '{label}'. {await self._where()}"

    async def fill_form(self, fields: list[dict[str, Any]]) -> str:
        if not fields:
            raise ToolError("fill_form needs at least one field.")
        done = []
        for f in fields:
            eid, value = f.get("element_id"), str(f.get("value", ""))
            loc = await self._locate(eid)
            tag = await loc.evaluate("el => el.tagName.toLowerCase()")
            typ = await loc.evaluate("el => (el.type || '').toLowerCase()")
            if tag == "select":
                try:
                    await loc.select_option(label=value, timeout=3_000)
                except Exception:
                    await loc.select_option(value=value, timeout=3_000)
            elif typ in ("checkbox", "radio"):
                if value.lower() in ("true", "yes", "on", "1", "checked", "check"):
                    await loc.check(timeout=3_000)
                else:
                    await loc.uncheck(timeout=3_000)
            else:
                await loc.fill(value, timeout=3_000)
            done.append(eid)
        return f"Filled {', '.join(done)}. Click the form's submit button to continue."

    async def screenshot(self, name: str, full_page: bool = False) -> str:
        self.shots_dir.mkdir(parents=True, exist_ok=True)
        path = self.shots_dir / f"{name}.png"
        await self.page.screenshot(path=str(path), full_page=full_page)
        return path.as_posix()

    async def take_screenshot(self, label: str = "shot") -> str:
        self._shot_n += 1
        safe = "".join(ch if ch.isalnum() or ch in "-_" else "-" for ch in label)[:40] or "shot"
        path = await self.screenshot(f"agent-{self._shot_n:02d}-{safe}", full_page=True)
        return f"Saved screenshot {path}"
