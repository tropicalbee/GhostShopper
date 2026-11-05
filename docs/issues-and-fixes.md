# Issues and fixes

## 2026-11-05 (Day 2-3)

**Playwright browser download outside the workspace**
- Broke: `playwright install` writes to `%LOCALAPPDATA%\ms-playwright` by default (outside the project).
- Fix: install and run with `PLAYWRIGHT_BROWSERS_PATH=0` (browsers inside `.venv`); `agent/browser.py` sets it by default. While the headless shell was still downloading, `PLAYWRIGHT_CHANNEL=chromium` ran the full build headless.

**`.env` is unreadable for the agent (deny rule)**
- Effect: the agent can't inspect secrets, by design. Groq status was read from `/api/health` (`groq_configured`), which reports presence only.
- For Day 2 runs the server was started with `PAYPAL_CLIENT_ID=" "` in the process env (not `.env`) so pages never loaded the real PayPal SDK.

**Clear-buy-button evidence selector longer than expected**
- Broke: e2e test expected `div.act.act-a`; evidence held `div.product > div.product-info > div.actions > div.act.act-a`.
- Root cause: test was too strict; the full path is better evidence. Fix: assert the suffix.

**`<paypal-button>` listed with an empty label**
- Broke: `find_elements` showed `e4 paypal-button ''`, so an agent couldn't tell what it was.
- Root cause: `innerText` doesn't see shadow DOM, where web components render their text.
- Fix: name falls back to the open shadow root's text, then to the tag name ("paypal button").

**Health test pinned the exact JSON**
- Broke: Day 1 `test_health` failed once `groq_configured` / `paypal_mode` were added.
- Fix: assert the stable keys, check the new ones by type.

**Mock popup opens as about:blank first**
- Risk: popup screenshot/URL taken before the SDK points it at the PayPal page.
- Fix: wait until the popup leaves `about:blank` (within the popup timeout) before recording evidence.

**PowerShell `Remove-Item Env:...` denied**
- The no-deletion rule covers it. Not needed: each shell call starts with a clean environment.

## 2026-11-05

**pytest could not create temp dirs**
- Broke: every test using `tmp_path` errored with `PermissionError: [WinError 5] Access is denied: ...\Temp\pytest-of-shiba`.
- Root cause: pytest's shared base temp dir is not accessible in this sandboxed Windows environment; a fresh `tempfile.mkdtemp()` dir is.
- Fix: root `conftest.py` overrides `tmp_path` with `tempfile.mkdtemp(prefix="ghostshopper-test-")`. No automatic deletion.

**Jinja macro not visible in child templates**
- Broke (caught before running): `price()` macro defined in `base.html` is not callable from templates that extend it.
- Root cause: Jinja child templates only override blocks; top-level macros in the parent are not exported.
- Fix: moved it to `store/templates/_macros.html`, imported with `{% from "_macros.html" import price with context %}`.

**Two over-strict test assertions**
- Broke: `"FH-MUG-01" not in html` failed because the SKU is in the buy URL; `'class="act' not in html` matched `class="actions"`.
- Root cause: test assertions, not store behavior.
- Fix: assert on `SKU:` / `In stock` text and `'class="act '` (with trailing space).
