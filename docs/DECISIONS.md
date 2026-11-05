# Decisions

## 2026-11-05

- **PayPal JS Web SDK v6**, not v5. v6 is current; v5 is security-fixes only. Client-ID auth (no client token), per the set-up docs. Rejected: v5 `sdk/js?client-id=` (deprecated).
- **Sandbox hardcoded.** `PAYPAL_API_BASE` and SDK URL are constants, no env switch. Rejected: `PAYPAL_ENV` toggle (invites a live misconfig).
- **One FastAPI process serves API + store** (store is a mounted sub-app). One Render free service, same origin for the PayPal button's API calls, no CORS. Rejected: separate store service (two cold starts, CORS, more deploy work).
- **Store is server-rendered Jinja2**, not React. Flaws must exist in the HTML an agent fetches (JSON-LD present or absent server-side). Also keeps it plain, like a real small-merchant site.
- **Server prices orders from `store/products.json`.** The browser sends SKU + quantity only.
- **Capture only orders we created** (checked in SQLite), and validate the order id format.
- **Flaws default ON** so a fresh deploy is the "bad store" for the demo. Toggles stored in SQLite (`store_flaws`), editable by form or JSON.
- **Price image drawn as SVG line segments, no `<text>`,** with an opaque file name, so neither the DOM, the SVG source nor the URL leaks the price.
- **Store checkout is quantity 1.** Backend accepts 1-10. Scope lock: one product flow.
- **No auth on `/store/admin`.** Demo control panel; no accounts per scope lock. Risk: anyone with the hosted URL can toggle flaws.
- **Docs set (Day 1):** CLAUDE.md DOCS section is canonical. `BUILD_LOG.md` is replaced by `issues-and-fixes.md`, `TODO.md` by `PLAN.md` checkboxes. Kept `DECISIONS.md`, `METRICS.md`, `CHANGELOG.md` (needed for submission).

## 2026-11-05 (Day 2-3)

- **Test seams chosen without the user (away):** `scoring.compute_score` (pure), `checks.evaluate_*` (page facts -> outcomes), and full runs (real loop + real browser + real store, replayed LLM). Rejected: unit tests of loop internals with mocked Playwright (would pass while the real browser path breaks).
- **Mock LLM = replayed cassettes**, as asked. Hand-recorded OpenAI-format assistant turns; `RecordingLLM` saves live Groq runs in the same format. Element ids are assigned in DOM order so replays are stable. Rejected: a heuristic "fake agent" (would be a fixed script pretending to be an LLM). Replay fails loudly when it runs out or calls a tool not offered.
- **Groq via httpx on the OpenAI-compatible endpoint**, not the `groq` SDK: no new dependency, same message format as the cassettes.
- **`checks` table holds every outcome (pass, fail, not tested); `failures` is a view.** The score needs passes too, and "not tested" must be distinguishable from "failed". One outcome per check per run (first wins).
- **Unreached checks:** `product_found` / `checkout_reached` count as failed (they are the agent's goal); later checks are "not tested" with the reason. Both score 0. Browse-only runs therefore max out at 80.
- **Score weights** (rules `2026-11-05.1`): discover 10, details 50 (price 15, JSON-LD 15, buy button 15, stock 5), checkout 20, payment 20. Fixes ordered by failed-before-untested, points, severity.
- **Detectors read the live DOM after every step**, independent of what the LLM asked for, so the LLM can't skip or fake a check. Price must be in `<main>` text (the "$50 free shipping" banner doesn't count).
- **"Extra step" = a form the agent had to fill between product page and checkout.** Revisiting the product page resets the path, so wrong turns aren't counted as extra steps.
- **Agent restricted to the store's origin; the generic `click` refuses the PayPal button.** Payment only via `pay_with_paypal`, offered only in checkout runs.
- **Credentials:** the payment tool owns them; the LLM only sees "sign-in is handled". Redactor scrubs them from every DB write as a backstop; `BuyerCredentials` repr is masked; popup screenshot only before typing; failure evidence is the store page only.
- **PAYPAL_MODE on the server (sandbox | mock), not a browser-level network intercept.** The fake Orders client is needed server-side anyway, and a human can click through the mock popup too. Mock pages copy PayPal's login element ids so the agent code is identical. Mode is shown in `/api/health`; the agent refuses if its requested mode differs from the server's. Rejected: Playwright route interception of the real SDK URL (server would still need fake orders).
- **Live checkout refuses to start** without PayPal app credentials on the server and both buyer variables. No fallback to mock.
- **Mock fees use PayPal's US rate 3.49% + $0.49** so numbers look like real captures ($24.00 -> $1.33 fee).
- **Kernel deferred.** On the D3 plan line, but the Day 3 brief was local Playwright + mocks; `BrowserSession` is the seam for it.
- **Playwright browsers inside `.venv`** (`PLAYWRIGHT_BROWSERS_PATH=0`), so nothing is installed outside the workspace. `PLAYWRIGHT_CHANNEL` can point at installed Edge.
- **Async tests via anyio's pytest plugin** (already installed with Starlette) instead of adding pytest-asyncio.
