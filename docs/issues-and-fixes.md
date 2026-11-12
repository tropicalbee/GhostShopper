# Issues and fixes

What broke, why, and what we did about it. Newest first.
Entries before 2026-11-10 are in [archive/issues-and-fixes-2026-11-05-to-11-09.md](archive/issues-and-fixes-2026-11-05-to-11-09.md). The full original file, before the split: [issues-and-fixes.md at a44951e](https://github.com/tropicalbee/GhostShopper/blob/a44951e642b2f8d88d750b7c7eaa2519ad2afeab/docs/issues-and-fixes.md).


## 2026-11-12 (session 9)

### Headless PayPal approval stuck at the password step
Run 53 (WebMCP on Fernhill, headless) created the PayPal order but the buyer approval stopped at PayPal's password step, so nothing was captured. Cause: PayPal's login does not finish in a headless browser. Fix: none in code; live PayPal approval runs headed, as runs 31, 34 and 50 did.

### The discover command used the shim only
`webmcp discover` installed the JS shim and never asked the browser for its own tools. Fix: it launches Chromium with `--enable-features=WebMCP` and reads the CDP WebMCP domain first. The shim is the fallback, and the report names the source.

### Showcase price parsing and product_found on a generic target
Run 55 on PayPal's showcase misread the price, and product_found was judged against a generic target. Fix: both corrected. Run 56 then bought the $25.00 gift card with prices consistent.

### Catalog check hit 429s and showed a misleading 0 of 1
Opening product pages quickly on the Shopify demo store got HTTP 429, and one readable page gave a 0 percent figure. Fix: one page at a time, 2 s apart, Retry-After honoured, a 60 s budget, and no percent when too few pages could be read.

### Run 58 was not a vision test
With only `price_as_image` on, the JSON-LD still had the price, so the shopper read 24.00 USD from structured data and never called `look_at_page` (84/100, order #1077 Paid). A vision test must remove every text source of the price. Run 59 (`price_as_image` plus `no_structured_data`) is the valid test: the shopper used vision at step 6 and bought.

### Health test pinned the old fields
The full suite had one failure: a health-keys test listed the old `/api/health` fields. Fix: updated for the new field.


## 2026-11-12 (session 8)

### First video edit judged choppy and off-message
Too many row cuts, caption pills and a story where the agent never paid, so PayPal barely showed. Fix: a new story built on run 50's real payment mismatch, one continuous voice, shots anchored to voice lines, no captions.

### The tour recorder couldn't encode its frames
A relative output path broke ffmpeg's concat list. Fix: resolve the output path in `record_tour.py`.

### Old fixed run kept the PayPal option flaws on
The admin scene only unticked the agent flaws. Fix: it now unticks exactly the bad-run flaws and checks that every flaw is off.

### Landing page example disagrees with the code
The landing's sample score lists "Order never marked paid -13", but the trace never changes the score. Not fixed yet; the video leaves that section out.


## 2026-11-12 (session 7)

### Live take stopped at a PayPal page the agent didn't know
Run 43 reached the Sandbox popup and was handed to a human at `/webapps/hermes`. Likely cause: PayPal's review page shows its "Pay with" inputs before its pay button, and `popup_state` called that unknown on the first poll. Fix: `unknown_grace_s` (12 s live) before asking a human, and a `paypal-popup-needs-human.png` screenshot when it does. The video take then used the vault payment, which has no popup.

### NVIDIA Nemotron 120B slow, then down
About 40 s per reply, and run 45 failed on `503 content safety screening is temporarily unavailable`. A one-word probe took 43 s after two 503s. Not our code. Fix for the video: `LLM_MODEL=nvidia/nemotron-3.5-lightning-30b-a3b` for the recording server only (2.5 s per reply, tool calls fine).

### Playwright video too soft to zoom
The built-in recorder writes 1 Mbps VP8. `record_demo.py` now saves CDP screencast frames at 1.5x density and encodes them with x264 itself.

### Recorder pointed at missing markup
The AG Grid row selector was wrong and failure rows have no expand view. The recorder now hovers row 0 and zooms on the grid instead.

## 2026-11-11 to 11-12 (session 6)

### Hosted run 1 died with a bare ReadTimeout
After 469 s and 16 steps the first hosted check stopped with `ReadTimeout:`. Cause: one Nemotron reply took longer than the 60 s httpx read timeout, and the LLM client retried only 429 and 5xx responses. Fix: `_post_with_retry` in `backend/app/agent/llm.py` now retries timeouts and dropped connections with backoff, and a final failure names the provider.

### Opening the sandbox to everyone exposed the sandbox buyer's browser
The security audit found that a visitor who starts a real-payment run would receive the Kernel live-view link whenever PayPal shows a captcha, and that browser has just logged in as the sandbox buyer. Fix: only the presenter gets the link, and other visitors' runs fail the human step at once instead of holding the run lock.

### Smaller audit fixes
Failing requests no longer spend the shared daily caps, a wrong `X-Admin-Token` header shares the unlock throttle, a fresh owner cookie always comes with `Cache-Control: private, no-store`, the SSRF check refuses 100.64.0.0/10, orders of deleted runs are hidden from other visitors, and the example bundle no longer carries sandbox payer ids or the shipping address.

## 2026-11-11 (session 5)

### Diagram redraw stalled twice
Two subagent attempts ran about 20 minutes each without editing the file. Cause: the brief asked for a layout problem (no crossings) to be solved inside a large skill workflow. Fix: redrew it directly. The crossings came from the column order, so Pay flows moved next to the shopper loop and PayPal moved above the browser, with the Checkout to PayPal arrow routed round the right edge.

### README showed the old UI
The README screenshots were from Nov 7, before the Nov 10 redesign. Fix: cropped panels from today's full page captures of runs 30 and 34 into `docs/screenshots/2026-11-11/`, downscaled to 900 px.

### Banner arrow turned into mojibake
Rewriting the SVG with PowerShell 5 `Get-Content` read it as ANSI and broke the arrow character. Fix: the arrow is now the `&#8594;` entity.

## 2026-11-11 (security audit before the public deploy)

### Rate limits could be dodged with a forged X-Forwarded-For
The Dockerfile trusts every proxy (`--forwarded-allow-ips='*'`), and uvicorn then reports the leftmost X-Forwarded-For entry as the client address. That entry is whatever the caller wrote, so a fresh fake address and a fresh owner cookie on each request got past every limit (runs, market check, PayPal orders). Fix: the limiter reads the entry `TRUSTED_PROXY_HOPS` from the right (default 1, the one Render appended) and falls back to the socket address when the header is missing. Process-wide daily caps now sit behind the per-address limits (`RUN_DAILY_CAP` 40, `MARKET_DAILY_CAP` 100, `ORDER_DAILY_CAP` 100). A request with the presenter's unlock cookie skips both, so the single run slot can't lock the presenter out.

### Anyone could switch the mock PayPal scenario
`PUT /mock-paypal/scenario` had no check, so a visitor could make the shared fake PayPal fail for everyone. It now needs developer options or the unlock cookie, and answers 403 otherwise. The seed script, the trace benchmark and the e2e tests only call it with developer options on.

### Store fetches buffered whole responses and could be rebound
The preflight and robots.txt fetches read the entire body, so a huge page could use up the 512 MB instance. They now stream: robots.txt stops at 512 KB and the preflight reads no body. The SSRF check also resolved a name once and let httpx resolve it again, so a rebinding name could reach a private address. A pinned transport now resolves once, refuses the name if any address is private, and connects to that address with the original Host header and TLS name. The error for a store that answers with an error no longer includes the status code.

### Admin unlock had no throttle and a raw cookie
`POST /store/admin/unlock` allowed unlimited guesses and stored the token itself in the cookie. It is now limited to 10 attempts per 15 minutes per address, and the cookie holds an HMAC of the token (checked with a constant-time compare).

### Smaller items
A bad `max_amount` on the agent order endpoint raised an unhandled error (500); it is now a 422 `BAD_MAX_AMOUNT`. The Docker image runs as a non-root user, sets `DEV_OPTIONS=0`, skips the Chromium install unless built with `INSTALL_CHROMIUM=1`, and `backend/requirements.txt` is pinned to the versions in `.venv`.

## 2026-11-11 (session 4: live runs, Kernel)

### Live run stopped at config
`LLM_PROVIDER=nvidia` was unknown. Only `openai-compatible` plus a base URL was supported. Fix: an `nvidia` provider with the NVIDIA base URL.

### "Not tested: never reached the product page" on runs that reached it
The reason was a stage level fallback. Fix: per check reasons when the stage was reached (currency_stated, price_consistent, buy_button_unobstructed).

### Two pytest runs at once collided and hung
The agent started a second run while one was going. Fix: one run at a time, in the foreground with a timeout.

### Kernel run hung on Shopify
Run 36 hung about 8 minutes and was killed by hand. Shopify registers a service worker. Over CDP the context route handler received its requests, and in Playwright both the frame access and continue raise, so the requests were never resolved. Fix: service workers blocked locally and bypassed in Kernel (`Network.setBypassServiceWorker`), the request guard never raises, inactivity timeout 300 s, run limit 600 s, session always deleted on error, timeout, cancel or Ctrl+C. Run 37 finished in 19 steps. Run 36 still shows "running" in the local DB.

### Browser tests opened start.duckduckgo.com and failed
Error: "Only pages on 127.0.0.1 can be opened". `BROWSER_PROVIDER=kernel` in the developer's `.env` made tests use Kernel cloud browsers, which can't reach localhost. Fix: set `BROWSER_PROVIDER=local`, and the root `conftest.py` now forces local and blanks paid keys.

### Ledger: Transaction Search NOT_AUTHORIZED
The "Transaction search" feature was not enabled on the sandbox REST app. After enabling it PayPal took a while to add the scope, and the running server kept an old token. Fix: enable the feature, wait, restart the server. Rows for runs 18, 31, 32 and 34 now show matched.

### Trace benchmark miss: store order without a PayPal id
The trace guessed "never charged". Fix, by user decision: PayPal stages unknown plus the mismatch `paid_without_paypal_reference`. Benchmark is 33/33.

### Open: flaky matrix test
`test_trace_matrix` subset test failed twice under load, then passed in later full runs. Cause not verified.
