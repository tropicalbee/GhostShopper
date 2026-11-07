# Decisions

What we chose, why, and what we turned down. Newest section last.

## 2026-11-05: Day 1

- We use the PayPal JS Web SDK v6. v5 (`sdk/js?client-id=`) only gets security fixes now. Auth is the client ID, as the set-up docs recommend for one-time payments; no client token.
- Sandbox is hardcoded. The API base and SDK URL are constants with no env switch, because a `PAYPAL_ENV` toggle is one typo away from live payments.
- One FastAPI process serves the API and the store (the store is a mounted sub-app). That's one Render service, and the PayPal button's API calls stay same-origin, so there's no CORS. A separate store service would have meant two cold starts and more deploy work.
- The store is server-rendered Jinja2. The flaws have to exist in the HTML an agent fetches (JSON-LD there or not), and it keeps the store looking like a real small shop.
- The server prices every order from `store/products.json`. The browser only sends SKU and quantity.
- We only capture orders this server created (checked in SQLite), and we validate the order id format first.
- Flaws default to on, so a fresh deploy is the bad store for the demo. Toggles live in SQLite (`store_flaws`) and can be changed by form or JSON.
- The price image is drawn from SVG line segments with no `<text>`, under an opaque file name. Neither the DOM, the SVG source nor the URL gives the price away.
- Store checkout is always quantity 1 (the backend accepts 1-10). Scope lock: one product flow.
- `/store/admin` has no login. It's a demo control panel and the scope lock rules out accounts. The risk: anyone with the hosted URL can flip flaws.
- Docs: the DOCS section of CLAUDE.md is canonical. `issues-and-fixes.md` replaces `BUILD_LOG.md` and the PLAN.md checkboxes replace `TODO.md`. We kept DECISIONS, METRICS and CHANGELOG because the submission needs them.

## 2026-11-05: Days 2 and 3

- I picked the test seams myself while the user was away: `scoring.compute_score` (pure), the `checks.evaluate_*` detectors (page facts in, outcomes out), and full runs (real loop, real browser, real store, replayed LLM). I skipped unit tests of loop internals with Playwright mocked out, since those can pass while the real browser path is broken.
- The mock LLM replays recorded responses ("cassettes"), as asked. They're OpenAI-format assistant turns, and `RecordingLLM` saves live Groq runs in the same format. Element ids follow DOM order so replays stay stable. Replay fails loudly if it runs out or calls a tool the run doesn't offer. A rule-based fake agent would have been a fixed script pretending to be an LLM, so we didn't do that here.
- Groq is called over its OpenAI-compatible endpoint with httpx. No `groq` SDK dependency, and the message format matches the cassettes.
- The `checks` table stores every outcome, passes included, and `failures` is a view over it. The score needs the passes, and "not tested" has to be told apart from "failed". Each check gets one outcome per run; the first one wins.
- If the agent never reaches the product page or checkout, product_found and checkout_reached fail; those were its goals. Checks after that are "not tested" with the reason. Both earn 0, so browse-only runs top out at 80.
- The first weights (rules `2026-11-05.1`) were discover 10, details 50 (price 15, JSON-LD 15, buy button 15, stock 5), checkout 20, payment 20. The weights section below replaces them.
- Detectors read the live DOM after every step, whatever the LLM asked for, so the LLM can't skip or fake a check. The price has to be in `<main>`: the "free shipping over $50" banner doesn't count.
- An extra step means a form the agent had to fill between the product page and checkout. Going back to the product page resets the path, so wrong turns aren't counted.
- The agent can only open pages on the store's origin, and the generic `click` refuses the PayPal button. Paying goes through `pay_with_paypal`, which only checkout runs offer.
- The payment tool owns the buyer credentials; the LLM is only told sign-in is handled. As a backstop, a redactor scrubs them from every DB write and every message sent to the LLM. `BuyerCredentials` has a masked repr. The popup is screenshotted only before anything is typed, and failure evidence is always the store page.
- Mock PayPal is a server mode (`PAYPAL_MODE=mock`). We needed a fake Orders client on the server anyway, and a person can click through the mock popup too. The mock pages copy PayPal's login element ids, so the agent code is the same in both modes. `/api/health` reports the mode, and the agent refuses to run if its mode and the server's differ. Intercepting the real SDK URL in Playwright would still have left the server needing fake orders.
- Live checkout won't start without the PayPal app credentials on the server and both buyer variables. It never falls back to mock.
- Mock fees use PayPal's US rate of 3.49% + $0.49, so the numbers look like real captures ($1.33 on $24.00).
- Kernel waited until the browser seam was in place. `BrowserSession` is that seam.
- Playwright's browsers are installed inside `.venv` (`PLAYWRIGHT_BROWSERS_PATH=0`), so nothing lands outside the workspace. `PLAYWRIGHT_CHANNEL` can point at the installed Edge.
- Async tests run on anyio's pytest plugin, which already ships with Starlette. No pytest-asyncio.

## 2026-11-05: tasks 1 to 11

### Scoring policy

- A failure's cause comes from its code, not from the check. The same check can fail because of either side: a popup can fail because of a store bug or a browser blocker, and a capture because of an integration error or a declined card. So each detector emits a code, and `failures.FAILURE_TYPES` maps the code to a cause and a fix. An unknown code counts as the store's fault, so nothing gets waved away by accident.
- If something isn't the store's fault, we exclude it and renormalize. Crediting the points instead would turn "never tested" into points. Renormalizing keeps the score meaning "the share of what the store controls that worked". Checks that an environment failure stopped from running are excluded too. Taking the points off anyway would punish the store for the buyer's bank.
- A declined capture (`capture_declined`) excludes capture_completed, payment_verified and task_completed, 15 points in all. A store that did everything else right scores 100, judged on 85 points, and the scorecard says why.
- The run outcome (purchased, reached_checkout, blocked, gave_up, error) comes from the checks. The LLM's own claim goes into `agent_report` and nothing reads it for scoring.
- task_completed ("fix the failures above") always lists after the failures that caused it. At 5 points it used to outrank a 4-point PayPal button failure, which put a useless instruction at the top.

### Why each check weighs what it does

Rules `2026-11-05.3`, 100 points in total.

- product_found, 5: it almost always passes, and when it fails everything after it fails too, so a big weight would count the same problem twice.
- price_in_text, 12: an agent that can't read the price can't decide to buy. Joint highest.
- currency_stated, 3: matters, but it's rarely ambiguous in a single-currency shop.
- structured_data, 12: JSON-LD is how agents and catalog feeds like Store Sync read a product. Joint highest.
- stock_readable, 4: needed for the decision, though an agent can often find out at checkout.
- stock_consistent, 3: a sold-out item that still sells wastes a purchase, but it's uncommon.
- image_alt_text, 3: helps image-aware agents and accessibility; it doesn't block a purchase.
- sale_claim_consistent, 3: a trust and compliance problem that doesn't block a purchase.
- clear_buy_button, 10: after the price, the most common thing that stops an agent outright.
- buy_button_unobstructed, 4: it blocks the click, but the banner can usually be dismissed.
- no_extra_steps, 6: costs steps and adds risk, but an agent can get through it.
- checkout_reached, 6: the browse goal itself; moderate because whatever causes it to fail is scored separately.
- price_consistent, 4: an agent should refuse a surprise price. payment_verified catches it again in checkout runs.
- paypal_button_found, 4: no button, no payment.
- popup_opened and payment_approved, 3 each: mostly PayPal's side, and often excluded.
- capture_completed, 5: the purchase actually went through.
- payment_verified, 5: the money matches what the store advertised.
- task_completed, 5: a small summary weight, since what caused it is already scored.

### Human approval

- If PayPal shows a CAPTCHA, a verification step ("verify it's you", a one-time code) or a form we don't recognize, the agent stops and marks the run `awaiting_human`. We never try to solve or bypass these. Kernel's `stealth` setting turns on its CAPTCHA solver, so we always leave it off.
- The run resumes when the PayPal window closes, then confirms the capture as usual, so no resume endpoint is needed. If nobody approves in time, that counts as an environment failure.
- Locally, a person can only approve in a visible browser (`--headed`). On Kernel the live view URL is printed and saved on the run.

### Robustness

- Each step has 30 seconds. The payment step gets its own budget, including the wait for a human. An LLM call that takes over 120 seconds ends the run as an error, which isn't the store's fault. Three step timeouts in a row also end the run.
- Loop detection looks for the same tool with the same arguments on the same page. The second repeat adds a warning to what the agent sees, and the third ends the run. The count resets when the agent moves to another page: going back to the product to try the next button is exploring, not looping. The scripted navigator showed us we needed that reset.

### Verification and market check

- Verification runs on the server (`/api/paypal/orders/{id}/verify`) and compares against the catalog's advertised price. When several things mismatch, a store-caused one becomes the primary code, so a store problem can't hide behind a PayPal one.
- Channel3 is called over httpx (`POST /v1/search` with `x-api-key`) rather than through its SDK. Without a key we use hand-made fixtures in Channel3's response shape. Every report says `source: recorded` and the fixtures use the reserved `.example` domain. The market check never affects the score.
- "Competitive" means at most 10% above the median of similar products. "Findable" means at least 3 comparable products in the same currency.

### Kernel

- Kernel is an explicit switch (`BROWSER_PROVIDER=kernel` or `--browser kernel`); having the key isn't enough to turn it on. Cloud browsers cost money, and they can't reach `localhost`, so they only work against a public store URL. We use Kernel's REST API over httpx plus Playwright's `connect_over_cdp`, and the session is always deleted afterwards. In tests, a local Chromium stands in for Kernel's browser.

### Saboteur and evaluation

- Ground truth is computed from the whole set of flaws, because flaws hide each other. With the price drawn as an image, for example, you can't compare it with the checkout price. Hidden ("masked") checks are left out of precision and recall rather than counted as misses.
- The benchmark uses a scripted navigator and labels it as not an LLM. Cassettes can't adapt to a store that changes on every run, and Groq's free tier can't pay for hundreds of runs. The navigator is enough to measure the detectors, which only need the pages visited. Measuring how a real agent behaves needs live runs.
- The cookie banner overlays the buy controls themselves, so whether it's detected doesn't depend on screen size or layout.
- `oos_buyable` marks the target product as sold out while it stays buyable. The agent never visits the item that's actually sold out, so a flaw there would never be seen.
- LLM flaw ideas go into `flaw_proposals` as "proposed". `expected()` refuses any flaw without a ground-truth label, so an idea can't enter a benchmark until it's a store toggle with a label.

### Judge

- Judge ratings have their own table, `judge_ratings`, and nothing in the scoring code reads it. Ratings made from a cassette are stored with `valid = 0`. A simple deterministic check also flags any number in an explanation that doesn't appear in the evidence.

### Deploy prep

- The Docker image includes Chromium for local runs, but the Render blueprint sets `BROWSER_PROVIDER=kernel` because the free tier has 512 MB of RAM. `.dockerignore` keeps `.env` out of the image. CI installs browsers with `PLAYWRIGHT_BROWSERS_PATH=0`. I haven't checked that the Actions versions we pin (checkout@v4, setup-python@v5, setup-node@v4) are still the current majors.

## 2026-11-06: Dashboard

- The look is light and monochrome: white cards on a light grey page, black and grey data, a segmented gauge and hatched bars, Geist and shadcn/ui. We turned down the dark zinc style from the first spec and the orange fintech references. Colour only means something here: green, amber and red for status and score change, red only for failures the store caused.
- The Simple view is the default on every screen size. The Advanced toggle only shows at 1024px and up. AG Grid and the bento grid don't work at phone width, and shopkeepers on phones need the three fixes, not the evidence table.
- Recharts draws the gauge, the stage bars, the score history and the market bars. AG Grid Community is used only for the failures table. Failure cells are one line with a tooltip, since wrapped rows with auto height broke the layout.
- "Send to my developer" is Copy, Download (`.md`) and a `mailto:` link. GhostShopper doesn't send email, so there's no mail service or key to manage. Mail bodies are cut at 1,800 characters because some mail apps drop longer `mailto:` links.
- Without a Groq key, the UI starts runs with the scripted navigator and labels them "Practice run (scripted shopper, not AI)". The demo store run also does the PayPal purchase in whatever mode the server is in (mock or sandbox).
- The two motion moments (score count-up, feed lines sliding in) are a small hook and a CSS animation, both off under `prefers-reduced-motion`. We didn't add Vengeance UI for two effects this small.
- Routes are hash based (`#/run/3`, `#/compare`), so a reload or shared link opens the same screen without a router dependency or server rewrites.

## 2026-11-06: Who can see a check

- Checks belong to a browser, not an account (the scope lock rules out accounts). The browser gets a random 256-bit token in an httpOnly, SameSite=Lax cookie, Secure on https, for 180 days. The database stores only its SHA-256, so a copied database can't be used to pose as a browser. We turned down unguessable share links: a merchant expects "my checks" to stay theirs, and a link pasted into a chat would expose them.
- A run you can't see answers 404, the same as a run that doesn't exist, so ids can't be probed.
- Runs with no owner (CLI and seed) are shared examples, readable by all and never deletable from the web. Runs made before this change are `unclaimed`: hidden from the web, kept for the CLI and metrics, never purged.
- Before and after only pairs checks of the same store from the same browser. The two-id endpoint stays, limited to your own checks of one store.
- Deployed servers refuse developer options and lock `/store/admin`, because the demo store is shared by every visitor and one person's toggles would change everyone's results. `DEMO_ADMIN_TOKEN` unlocks it for the presenter. "Deployed" means `APP_BASE_URL` isn't localhost, and `DEV_OPTIONS` overrides that.
- Rate limits are in memory, per client IP and per browser, and count failed attempts too (a failed start still costs a fetch of someone's site). This needs a single process, which the Dockerfile already uses. Uvicorn trusts Render's forwarded IP headers because the proxy is the only way in.
- Retention: owned checks older than 30 days are deleted at startup and before each new check, screenshots included. Delete removes the results and screenshots but keeps any sandbox order record, unlinked, because that belongs to the demo store.
- SSRF: every request the live-store browser makes must go to a public host (checked once per host per run), and the server's own fetches check each redirect hop before sending it. DNS rebinding between our check and the browser's own lookup stays open; closing it needs a pinning proxy, which is more than a demo needs.
- The dashboard's CSP allows inline styles only (AG Grid and Recharts set them); scripts are `'self'` only.

## 2026-11-06: The Ledger look

- The user rejected the first build as blank and raw, and named two references: ui.shadcn.com and their Razorpay Buildathon dashboard. Two static mocks came first: A, Ledger (square, ruled, mono figures) and B, Studio (soft cards, a ring chart). The user chose A and asked for less black, so impeccable's quieter pass removed the inverted score block, thinned the path bars to grey, and softened rules and ink.
- What we kept from Razorpay: the white ground, hairline borders, a dark rule under page and table heads, square corners, mono figures, tabular data. What we left out: all-caps tracked labels (hallmark and impeccable both treat them as an AI tell) and the big black blocks.
- The shopper's path replaced the gauge and the stage bars. It shows the same numbers, but as the route a shopper takes, with the reason written where it got stuck. A gauge only says "how much".
- Navigation is a left sidebar on desktop and a hamburger sheet on phones, at the user's request. It earns its place by listing the browser's recent checks, so a merchant can get back to a store in one click.
- ui-ux-pro-max suggested Swiss minimalism for this kind of product (kept) with a navy palette and Fira fonts (declined: the user pinned monochrome and the shadcn look).


## 2026-11-06: Any AI provider, speed and the things we left alone

### Provider layer
- `ChatModel` is an abstract base class, and the OpenAI chat-completions message and tool format is the one format inside the agent. `OpenAICompatibleChat` covers Groq, OpenAI, OpenRouter, Together, Ollama and any OpenAI-compatible URL. `AnthropicChat` translates to and from the Anthropic Messages API. It sends no temperature and no forced `tool_choice`, because current Claude models reject them.
- A provider is one entry in the `PROVIDERS` registry (name, adapter class, default base URL, whether a key is required). A provider with a new wire format needs one adapter class on top of that. Cassettes, the recorder and the loop didn't change, since they already speak the canonical format.
- Config comes from `LLM_PROVIDER`, `LLM_MODEL`, `LLM_API_KEY` and `LLM_BASE_URL`. `GROQ_API_KEY` and `GROQ_MODEL` keep working when the provider is empty or `groq`, so an existing `.env` doesn't break. A missing key, model or base URL is an `LLMConfigError`, never a fallback to mock.
- `make_llm` takes `live` or `mock`; `groq` stays as an alias for `live`. Both adapters use httpx directly, so there is no provider SDK dependency.

### Caching and headers
- Finished runs sit in an in-process LRU of 128, and market checks are cached for 10 minutes per SKU. Explain, delete and purge invalidate the run cache. Both are single-process shortcuts. A CLI explain in another process won't invalidate the server's cache until the server restarts.
- `/assets/*` is `public, max-age=31536000, immutable` because build output is content-hashed. `/api/rubric` is public for an hour. Every other `/api` response is `private, no-store`, since it is one browser's data. A response that sets a fresh owner cookie is never public.
- GZip applies to responses over 1,000 bytes. Starlette can't exclude by content type, so PNG screenshots are compressed too, for little gain.
- `GET /api/runs` pages with `limit` (1 to 100, default 50) and `before` (a run id). It stays a JSON array so existing callers keep working.

### Admin unlock
- The URL token is gone because it lands in access logs and history. `/store/admin` shows a form that posts to `/store/admin/unlock` and sets an httpOnly, SameSite=Strict cookie. The `X-Admin-Token` header still works for scripts.

### Things we turned down
- Load balancer. The app is one instance by design: the run lock and the rate limiter live in memory and SQLite sits on local disk. A second instance would break all three. Scaling would need a shared lock or queue, a shared rate-limit store, and Postgres or a single writer service.
- SQLite connection pool. A connection per request is the pattern SQLite recommends. WAL plus a busy timeout is the robustness fix.
- Input debouncing. No input in the dashboard does work per keystroke.
- Vendor chunk split. We tried it and reverted it: rolldown's forced groups broke React and CommonJS initialisation at runtime. The lazy Advanced chunk is already the split that matters.

## 2026-11-06: Demo store redesign

- The store looks like a standard Shopify theme, based on screenshots of a ceramics shop template ("Cerametica"). We turned down bolder art direction options. This overrides the "keep the store plain" line in CLAUDE.md for now.
- Product photos are saved locally in `store/static/img/`. Hotlinking Unsplash would break offline and Kernel runs and the JSON-LD image URL. Drawn illustrations looked worse. Credits are on `/store/credits`.
- The catalog has 12 products, not 13. A 13th left one card alone on the last row of the grid.
- The navbar has no cart and no newsletter button. The store has no cart (Buy now goes straight to checkout), and a mini cart would break the scope lock of one product flow. The newsletter signup lives in the footer.
- The store shows no "demo flaws on" badge. The flaws are explained only at `/store/admin`.
- Reviews use initial avatars. Stock photo faces on fictional reviewers felt wrong.
- Checkout and details pages keep exactly three controls before the form or PayPal button, so their ids (e4 to e7, and the PayPal button at e4) stay stable. Cassette ids were shifted only for the shop pages.
- The new SKUs got hand-made market fixtures, labelled "Not real market data" like the existing four. We turned down narrowing `test_market.py`, which requires a recording per catalog product.

## 2026-11-07: Real sandbox checkout

- The demo uses US sandbox accounts (business payee and personal buyer) with USD. We turned down the India sandbox business account: the payment failed with UNSUPPORTED_PAY..., and India accounts have real-world limits on receiving payments.
- A PayPal error page is classed as environment, not the store's fault. Payments only run on our own demo store, and the error comes from account setup. We turned down classing it as a store failure, and leaving it as a 120 second timeout that hides the cause.
- We are not using PayPal's AI-Toolkit (github.com/paypal/AI-Toolkit) for now. The shopper agent has to pay through the store's own PayPal button like a real shopper, and the backend already calls Orders v2 directly. It could be revisited for the verify step.

## 2026-11-07: PayPal features

- PayPal readiness is its own 0 to 100 figure, separate from the agent-readiness score. Folding it in would change the score's rubric and make old runs hard to compare.
- The budget is enforced in code before the PayPal button is clicked, never by the LLM. If the checkout total can't be read while a limit is set, the agent refuses to pay.
- The product feed is built from what the agent observed, not from the store's source, so the gaps it shows are the ones an agent really hits.
- Only the browser that owns a run can refund it. Shared examples and other browsers get 404.
- We turned down auto-refunding every run. Judges should see the capture first, then press the refund button.
- The feed is labelled "what you would submit". Store Sync has no public sandbox API, so we don't pretend to submit.

## 2026-11-08: Blockers and audit

- Real payment is chosen per run, and mock PayPal is the hosted default. A public server should not spend Kernel minutes or sandbox calls on every visit, but the presenter can still run the real sandbox purchase. We turned down making real payment the server default, a separate real-only deployment (two services and two cold starts), and a silent fallback to mock when keys are missing. The fallback would break the "never silently fall back" rule.
- Real runs use Kernel with headless off. Headless runs stopped at the sandbox password step (run 19), and Kernel's live view lets a person take over when PayPal stops the agent.
- Refunds use the client for the run's recorded PayPal mode. A mock order never reaches the sandbox API, and a sandbox order never reaches the mock.
- The four PayPal toggles are classic flaws only. The agent's eval matrix keeps the original four flaws (16 combinations), so earlier benchmark numbers stay comparable.
- The budget is checked on the amount the store charges, from its create-order response. Page text can be wrong, and the LLM never decides how much money is spent.
- We kept our Pay Later component name, `paypal-pay-later-button`, because the PayPal docs disagree with `paylater-button`. checkout.js falls back to plain PayPal payments if the SDK refuses a component.
- Real payment needs the presenter unlock (the `/store/admin` cookie) on a hosted server. Anonymous visitors and bots get the mock PayPal only, so nobody else can spend Kernel minutes. Dev servers are unchanged.
