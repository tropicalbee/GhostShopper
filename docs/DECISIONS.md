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
