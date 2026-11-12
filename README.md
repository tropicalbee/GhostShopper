<div align="center">

<img src="docs/assets/banner.svg" alt="GhostShopper. PayPal reports that in its test store, agent tools bought in 3 calls, while going through the page took 30+ steps." width="100%">

<br>

### A mystery shopper for the AI agent era

GhostShopper shops your store like an AI agent, shows where the purchase breaks, and proves the fixed checkout with a real PayPal Sandbox payment.

In one live run PayPal captured $24.00 while the store's own order still said Awaiting payment, and GhostShopper flagged the store order as the first mismatch.

[Repository](https://github.com/tropicalbee/GhostShopper) · [Architecture](#how-it-works) · [Results](#results) · [Run it locally](#run-it-locally)
Hosted demo: [ghostshopper.onrender.com](https://ghostshopper.onrender.com). The free tier sleeps when idle, so the first load may take about a minute.

<!-- HOSTED_URL -->
<!-- VIDEO_URL -->

`Python 3.11` · `FastAPI` · `Playwright` · `React + Vite` · `AG Grid` · `PayPal Orders v2 + JS SDK v6` · `NVIDIA Nemotron` · `WebMCP (Chromium, CDP)` · `Kernel` · `Channel3`

</div>

---

## Contents

1. [Why this exists](#why-this-exists)
2. [What it does](#what-it-does)
3. [See it](#see-it)
4. [How it works](#how-it-works)
5. [Engineering](#engineering)
6. [Results](#results)
7. [Impact](#impact)
8. [Run it locally](#run-it-locally)
9. [Limits and FAQ](#limits-and-faq)
10. [Credits](#credits)

---

## Why this exists

PayPal's WebMCP lets an agent buy through structured tools. In PayPal's test storefront that cut the journey from **30+ interface steps to three tool calls**. Structured tools only fix the browsing half, though. If the store's back end never marks the order paid, a WebMCP purchase breaks the same way a browser purchase does. PayPal's Store Sync docs say it "lets customers place orders directly into your existing order management systems". GhostShopper checks that the order actually lands there correctly.

So it runs the same purchase two ways: through the ordinary storefront with a browser agent (PayPal JS SDK v6 button, Orders v2), and through WebMCP tools. Both paths are checked against the same purchase trace: the intended purchase, the PayPal order, the capture, the store's order and what the store says afterwards. The browser path also gets evidence for each failure and a readiness score.

PayPal's Agentic Commerce Pulse Report (498 US merchants, Q1 2026) found that only about 1 in 5 merchants have 80% or more of their catalog as structured, machine-readable data, and that data security is the top barrier. GhostShopper's catalog readiness figure measures that 80% line. Its safety guard and tool checks speak to the security side: the agent never holds credentials, and the buyer approves in PayPal. Source: [the report](https://www.paypal.com/us/brc/article/agentic-commerce-pulse-report-findings).

Traditional checkout tests verify known paths. GhostShopper tests what happens when an AI shopper has to find the product, read the page and complete the purchase without human intuition.

What stops an agent is often invisible to a person:

- a price drawn into an image
- missing product data (no `Product` JSON-LD)
- a "Go" button that is really a `<div>`
- a cookie banner sitting on the buy button
- an extra form before payment

And when the agent does pay, nobody checks that the store recorded the same purchase PayPal captured.

## What it does

| Step | What happens |
|---|---|
| **1. Shop** | An LLM-driven agent browses the store, finds the product, reads the details and tries to check out. It picks every step itself. |
| **2. Diagnose** | Code checks every page the agent saw against 19 checks. Each failure comes with a screenshot and a fix in plain words. |
| **3. Pay** | The agent pays through the real PayPal Sandbox: JS SDK v6 button, buyer approval, Orders v2 capture. |
| **4. Verify** | The purchase trace compares five records of the same purchase wherever each record exposes them, and checks that they're linked by ID. |
| **5. Score** | A deterministic readiness score out of 100, fixes ranked by points, and a before/after comparison after the fixes. |
| **6. WebMCP path** | The same purchase through the store's WebMCP tools, with an 8-item tool checklist and a side-by-side comparison with the browser run. No readiness score: the score rates the page path. |
| **7. Vision (optional)** | The shopper can call `look_at_page` to read a store page's screenshot when the text fails, for example a price drawn into an image. The answer is treated as page content and never changes the score. |
| **8. Catalog readiness** | How many of up to 12 product pages carry machine-readable Product data. Informational, never part of the score. |

**What sets it apart is the purchase trace.** A payment can succeed while the store's order is wrong: captured but still pending, marked paid after a decline, duplicated on a retry. GhostShopper links the records by ID and flags each broken link. It got all 33 deterministic trace scenarios right (mock PayPal, demo store), and in live run 50 it caught a seeded one on real Sandbox data. The score comes second, as a summary of the checks along the way.

In live run 50 the shopper paid $24.00 through the Vault and PayPal captured it, but the store's order #1071 stayed Awaiting payment. The first mismatch was at the store order, all 4 of 4 ID links were ok, and readiness was 65/100. With every flaw off (run 51) it scored 100/100 and order #1072 was Paid. In run 52 a review hid a message aimed at AI agents. GhostShopper flagged it and the shopper did not follow it. Earlier live runs on the 120B Nemotron model went from 49/100 (run 31) to 100/100 (run 34), with the fixed store verified against the store's order ($22.67 net).

> **Positioning.** PayPal is building the infrastructure for agentic commerce through [Agent Ready](https://developer.paypal.com/agent-ready/overview) and [Store Sync](https://developer.paypal.com/store-sync/overview), two separate services under [Agentic Commerce Services](https://developer.paypal.com/agentic-commerce-services/about). GhostShopper helps a merchant check their purchase flow, on the storefront and through WebMCP tools, before and after they pursue those integrations. The readiness score and the WebMCP tool checklist come from GhostShopper's own checks. It is not an Agent Ready, ACP or UCP conformance test, and not a PayPal certification or eligibility check.
>
> There is also a Vault agent payment path (`POST /api/paypal/agent-orders`: saved vault id, idempotent request id, spending limit, server-side capture). It ran live in the PayPal Sandbox: runs 48, 50, 51 and 52 paid through it. It is not the same as Agent Ready delegated payment tokens.

## See it

The demo video tells the run 50 and 51 story above. These three screenshots are from the earlier live runs 31 and 34 (2026-11-11), on the demo store Fernhill Ceramics.

**Before: the flawed store scores 49/100 (run 31).** Each lost point names the fix.

<img src="docs/screenshots/2026-11-11/bad-store-score-49.png" alt="Readiness score 49 out of 100 with the failed checks and their fixes, next to the PayPal money panel" width="720">

**After the fixes: live 49 → 100, every fix accounted for.** Runs 31 and 34, both paid through the PayPal Sandbox.

<img src="docs/screenshots/2026-11-11/run31-to-34-before-after.png" alt="Before and after table from check 31 to check 34: total score 49 to 100, with each fixed check and the points it gained" width="720">

**The proof: one live Sandbox purchase with all four ID links verified (run 34).** $24.00 captured, $1.33 fee, $22.67 net.

<img src="docs/screenshots/2026-11-11/run34-trace-linked.png" alt="Check 34: purchase trace with the agent's intent, store order 1047, PayPal order and capture all matching, and all four ID links marked Linked" width="720">

## How it works

<img src="docs/diagrams/architecture.png" alt="Simplified architecture: the merchant's browser, the FastAPI app with the shopper agent and demo store, and PayPal, Kernel, Channel3 and the LLM" width="820">

The detailed version, with every file and twelve numbered steps, is in [docs/diagrams/architecture-detailed.png](docs/diagrams/architecture-detailed.png).

**One check, end to end**

1. The dashboard starts a check. The runs API prepares a browser and the model.
2. The shopper loop asks the model for the next tool: open a page, list elements, read text, click, fill, screenshot, pay.
3. The tool acts in the browser: local Playwright, or a Kernel cloud browser when hosted.
4. After every step, the check engine judges what the browser saw. No model is involved.
5. At checkout, the store creates its own order and a PayPal order. The buyer approves in PayPal's popup and the store captures.
6. The agent reads the store's order page back, and the trace compares the five records.

**The purchase trace**

| Record | Source |
|---|---|
| What the agent wanted | the run's target and the catalog price |
| The store's order | `store_orders`, page at `/store/orders/{n}` |
| PayPal's order | Orders v2 |
| PayPal's capture | Orders v2 capture, fees from `seller_receivable_breakdown` |
| What the store says afterwards | the order page, read back by code |

- Each field is compared wherever a record exposes it.
- A field a record doesn't expose is marked **unavailable** with the reason, and is never guessed.
- Broken ID links sort before field mismatches. If the records belong to different purchases, comparing their fields means nothing.
- The trace is built by code in `backend/app/trace.py` and never changes the score.

<img src="docs/diagrams/trace.png" alt="The purchase trace: records compared field by field where available, with the first mismatch flagged" width="720">

## Two paths

WebMCP lets a page register shopping tools that an agent calls directly. GhostShopper runs both paths on Fernhill and compares them.

1. The browser path is the shopper loop above: pages, clicks, the PayPal button.
2. The WebMCP path launches Chromium with `--enable-features=WebMCP`, so the page exposes native `document.modelContext`. GhostShopper finds the tools through the Chrome DevTools Protocol WebMCP domain (`WebMCP.enable`, `WebMCP.toolsAdded`) and calls them with `WebMCP.invokeTool` and `WebMCP.toolResponded`, like a browser-integrated agent. A small JS shim is a fallback only for browsers without native WebMCP (a Kernel browser, for example), and every report says which one was used.
3. The model picks every tool call: `shopping.searchProducts`, `shopping.getProduct`, `shopping.initiateCheckout`, `shopping.completeCheckout`. The runtime, never the model, signs the sandbox buyer in to PayPal to approve. Credentials never reach the model.
4. After checkout the runtime reads the store's order page back. The trace compares the same five records as on the browser path.
5. `compare` puts the two runs side by side, and code writes the verdict.

Whose tools are whose:

- On PayPal's own showcase ([webmcp-store.paypal.com](https://webmcp-store.paypal.com/merchants/gift-cards?sdk=v6)), GhostShopper uses PayPal's real tools and service. This is labelled "externally demonstrated, not GhostShopper-integrated". PayPal's WebMCP needs enablement through Store Sync, which is a request form, and we could not get it for our demo store.
- On Fernhill, the WebMCP tools are GhostShopper's adapter (`store/static/webmcp.js` and `POST /store/webmcp/rpc`). It implements the same `shopping.*` tool contract the showcase registers (names, schemas, result envelope, approval hand-off) and is wired to our own PayPal Orders v2 sandbox checkout. These are not PayPal's WebMCP tools.
- On live stores such as the Shopify demo store, WebMCP is discovery only.

The 8-item tool checklist (tools discovered, schemas valid, product found, price consistent, buyer approval required, hand-off to PayPal, checkout completed, order recorded) is computed by code. It is not a score.

## Engineering

### Design decisions

| Decision | Why |
|---|---|
| **A real tool-calling loop, not a script** | The model picks each action from what it saw. A loop detector warns on a repeated action and stops on the third. Runs are capped at 25 steps. |
| **A deterministic score** | Code records weighted checks, and the model never sees the weights. A changed score on a rerun means the store changed. |
| **Only the store's own failures cost points** | A declined card or a blocked popup is listed as "not the store's fault" and taken out of the denominator. |
| **Server-side pricing** | The PayPal order is priced from the catalog on the server, so a page can't talk the agent into a different amount. |
| **`custom_id` for the store order number** | `invoice_id` was rejected: PayPal refuses a repeated invoice id, and store numbers restart on a fresh deploy. |
| **Unknown over guessed** | A paid order with no PayPal reference makes the PayPal stages unknown and raises its own mismatch. |
| **Local Playwright, Kernel only when hosted** | Same tool interface for both. The test setup forces the local browser and blanks the paid keys. |
| **Any OpenAI-compatible model** | Any OpenAI-compatible endpoint works through `LLM_PROVIDER` with no code change. The recorded runs used NVIDIA Nemotron. |

Full log: [docs/DECISIONS.md](docs/DECISIONS.md).

### Security and trust

The agent reads third-party pages and touches a payment flow, so every limit is enforced in code, not in the prompt.

- **Page content is data.** It reaches the model inside `<page_content>` tags. `agent/injection.py` scans visible and hidden text (display none, off-screen, aria-hidden, alt text, comments) and `robots.txt` for instructions aimed at agents, and logs every hit in the agent safety report.
- **Hard limits.** No navigation to another host and no downloads. Password and card fields are refused. Live store requests must go to public hosts, with DNS pinned.
- **Vision.** `look_at_page` screenshots store pages only, never PayPal pages. The vision answer is framed as data and scanned for text aimed at agents, like any page content.
- **Credentials.** The sandbox buyer login comes from `.env` and is never logged, stored or screenshotted.
- **Deployed mode.** Developer options are refused, and `/store/admin` is locked behind `DEMO_ADMIN_TOKEN` with an HMAC cookie.
- **Abuse limits.** Per-client rate limits read `X-Forwarded-For` from the right, plus daily caps on runs, market checks and PayPal orders. The Docker image runs as non-root.

### Supporting services

| Service | Role |
|---|---|
| **PayPal** | JS SDK v6 button on the store, Orders v2 create and capture, fees from the capture |
| **WebMCP** | Chromium launched with `--enable-features=WebMCP`, tools discovered and called through the Chrome DevTools Protocol WebMCP domain. A JS shim is the fallback for browsers without native WebMCP. |
| **NVIDIA Nemotron** | The shopper's tool-calling model: the local database records `nvidia/nemotron-3.5-super-vl-120b-a12b` for runs 31 to 37, `nvidia/nemotron-3.5-lightning-30b-a3b` for runs 47, 48, 50, 51 and 52, and the Super VL 120B model again for runs 53 to 59 (runs 58 and 59 also used it for vision). Any OpenAI-compatible endpoint works through the same interface. |
| **Kernel** | Hosted cloud browser over CDP. Its live view lets a person finish PayPal's own checks. A browse-only Shopify run in Kernel matched the local run (62/100, same 5 issues). Hosted run 5 (2026-11-12) ran in Kernel on the hosted site and shopped the flawed demo store (41/75; failures price_in_text, structured_data, clear_buy_button, no_extra_steps, stock_readable). Its PayPal popup approval timed out at the password step after 120 s, so no order was captured. Every completed purchase so far ran locally. <!-- HOSTED_VAULT_RUN --> |
| **Channel3** | Market context for the product (similar listings and a median price), shown in the Advanced view. Live Channel3 search results were checked on the hosted site on 2026-11-12 (the recorded responses are the fallback, labelled as sample data). Not reliable price intelligence, and never part of the score. |
| **AG Grid Community** | Before/after and check grids in the dashboard |

## Results

Every number links back to [docs/METRICS.md](docs/METRICS.md). Live evidence and mock benchmarks are kept apart.

### Live: browser path vs WebMCP path, Nemotron 3.5 Super VL 120B + PayPal Sandbox (2026-11-12)

Same store and same flaws (price as image, no structured data, store never marks paid). Local Chromium.

| Run | Path | Outcome |
|---|---|---|
| 57 | browser agent, vault payment | 10 agent steps, 35 s, readiness 65/100 (price as text 12, structured data 12, stock 4 lost). PayPal capture COMPLETED $24.00 (fee $1.33, net $22.67). Store order Awaiting payment, first mismatch at the store order, 4 of 4 ID links ok |
| 54 | WebMCP on Fernhill | 4 tool calls plus the runtime's buyer approval and order read-back, 39 s. Capture COMPLETED $24.00. Store order #1075 still Awaiting payment, same first mismatch, 4 of 4 ID links ok. Price 24.00 in search, product, checkout and capture. Tool checks: 7 pass, order_recorded fail. No readiness score |
| 56 | WebMCP on PayPal's showcase (external demo) | Bought a Starbucks gift card at $25.00, buyer approved in the PayPal Sandbox, `completeCheckout` returned COMPLETED. Prices 25.00 in search, product and checkout. Tool checks: 7 pass, order_recorded not tested (no store order on PayPal's merchant). 76 s |
| 53 | WebMCP on Fernhill, headless | Order created (store cart #1074), but buyer approval stuck at PayPal's password step in a headless browser. Blocked, nothing captured. Live PayPal approval runs headed |

The compare verdict (57 vs 54, written by code): "WebMCP bought in 4 tool calls; the browser agent took 10 steps. Both paths hit the same first mismatch: the store order still says Awaiting payment." Wall time was similar (35 s browser, 39 s WebMCP) because the WebMCP path includes the buyer's PayPal approval page that the vault payment skips, so these runs do not show WebMCP being faster.

Discovery on other sites (native WebMCP, no purchase):

- PayPal's showcase: 4 tools (`shopping.searchProducts`, `shopping.getProduct`, `shopping.initiateCheckout`, `shopping.completeCheckout`). The page loads PayPal's web-sdk v6 core and PayPal's WebMCP script.
- The public Shopify demo store `sauce-demo.myshopify.com`, which we did not build and which has no PayPal SDK: 12 WebMCP tools (`ask_business`, `browse_store`, `cancel_cart`, `create_cart`, `get_cart`, `get_product`, `get_ucp_profile`, `manage_orders`, `proceed_to_checkout`, `search_catalog`, `show_variant`, `update_cart`). Its robots.txt and tool descriptions contain text aimed at agents, which GhostShopper treats as data.

Catalog readiness: the demo store is 12/12 machine-readable with flaws off and 0/12 with `no_structured_data` (also 0/12 with `currency_missing`). On `sauce-demo.myshopify.com` it found 3 product pages and checked 2: 0 of 2 machine-readable (no Product JSON-LD, matching runs 33 and 37). The third page was refused with HTTP 429 after polite retries, so no percent is shown. It loads one page at a time, 2 s apart, honours Retry-After, stops at a 60 s budget and shows no percent when too few pages could be read.

### Live: shopper vision, Nemotron 3.5 Super VL 120B + PayPal Sandbox (2026-11-12)

The shopper has an optional `look_at_page` tool: a viewport screenshot of the store's own page, with a question for the vision model. Store pages only, never PayPal pages. Both the shopper and `VISION_MODEL` were `nvidia/nemotron-3.5-super-vl-120b-a12b`. Vault payment, headed.

| Run | Store | Outcome |
|---|---|---|
| 59 | price as image + no structured data (the price exists only as an image) | At step 6 the shopper called `look_at_page` ("What is the price and stock status of the Speckled Stoneware Mug?") and the vision model answered "The price is $24.00 and it is in stock (ships from Asheville in 3 business days)." It then bought the mug in 12 steps: capture COMPLETED $24.00 (fee 1.33, net 22.67), store order #1078 Paid. Readiness stayed 65/100 |
| 58 | price as image only (JSON-LD still had the price) | Vision was available, but the shopper never called `look_at_page`. It read 24.00 USD from the structured data and bought: 84/100, order #1077 Paid |

Vision does not change the score. Price in text, structured data and stock readable still failed in run 59, because Store Sync, WebMCP and catalog-reading agents need that data as text. Run 58 shows the agent used its eyes only when text failed.

### Live: Vault payment, Nemotron 3.5 Lightning + PayPal Sandbox (2026-11-12)

| Run | Store | Score | Outcome |
|---|---|---|---|
| 50 | price as image, no product data, store never marks paid | **65/100** | purchased: PayPal capture COMPLETED $24.00, fee $1.33, net $22.67. Store order #1071 still Awaiting payment, first mismatch at the store order, 4 of 4 ID links ok |
| 51 | all flaws off | **100/100** | purchased: store order #1072 Paid, 4 of 4 ID links ok, no mismatches |
| 52 | hidden instructions for AI agents | n/a | purchased at $24.00 in 11 steps. One finding at step 2 (off-screen review text, hidden from people), and the shopper did not follow it |
| 48 | fixed store | **100/100** | purchased in 11 steps: $24.00 captured, $22.67 net, 4 of 4 IDs linked |

Run 50 to 51 gained 35 points: price as text 12, structured data 12, stock readable 4. The payment mismatch itself costs no points, because payment-state mismatches are reported apart from the readiness score.

### Earlier live runs: Nemotron 120B, popup login, PayPal Sandbox (2026-11-11)

| Run | Store | Score | Outcome |
|---|---|---|---|
| 31 | demo store, classic flaws on | **49/100** | purchased: $24.00 captured, $1.33 fee, $22.67 net |
| 32 | demo store, fixed | **100/100** | purchased |
| 34 | demo store, fixed | **100/100** | purchased as store order 1047, **all 4 ID links ok**, PayPal echoed `custom_id=1047` |
| 33 | public Shopify demo store, browse only | 62/100 | same 5 issues found locally |
| 37 | same Shopify store, in Kernel | 62/100 | same 5 issues in the cloud browser |

Run 36 hung about 8 minutes on service-worker requests before a fix. Runs 33 and 37 are a portability check on a store GhostShopper didn't build. They don't validate it on real stores.

### Benchmarks: mock PayPal, scripted navigator, demo store

These check the detectors and the trace against hand-written labels on the demo store. A perfect score here is a consistency check.

| Benchmark | Measures | Result |
|---|---|---|
| Purchase trace, 33 deterministic scenarios | first mismatch found, no false alarms, no guessing | **33/33 deterministic trace scenarios passed** (mock PayPal, demo store), 0 false mismatches on healthy runs, 5/5 broken links found |
| Flaw detection, 16 classic combinations | each check fires only when its flaw is on | precision 1.0, recall 1.0 (40 TP, 0 FP, 0 FN) |
| Flaw detection, 30 random combinations of 10 flaws | the same on a wider mix | precision 1.0, recall 1.0 (105 TP, 0 FP, 0 FN) |
| Full test suite | unit, API and browser e2e | 657 tests. Full run on 2026-11-12: 646 passed, 11 failed in 13 min; all 11 were test setups that started runs on a server with no LLM (now refused by design) or listed the old health keys. After fixing those setups, both files pass (59 passed). |
| WebMCP tests | rpc, discover, e2e, compare, checks, api, plus catalog readiness | 85 passed (that file plus all WebMCP test files) |

### Reproduce them

```bash
python -m pytest                                              # full suite
python -m backend.app.eval benchmark --matrix trace           # purchase trace, 33 scenarios
python -m backend.app.eval benchmark --matrix classic         # flaw detection, 16 combinations
python -m backend.app.eval benchmark --matrix random --n 30 --seed 7
```

Run them with the virtualenv's Python: `.venv\Scripts\python` on Windows, `.venv/bin/python` on macOS and Linux. Browser tests skip if Chromium isn't installed.

The hosted demo, the no-key local runs and every live result (with the keys to get and the exact commands) are in [docs/REPRODUCE.md](docs/REPRODUCE.md).

## Impact

- For small merchants, the full five-record trace works on the demo store: a paid order the store never marked as paid (run 50) is found, with the record that disagrees named. On other stores GhostShopper reports what the agent could read and do, and the store order stays unknown. Then a list of fixes in plain words, each with a screenshot of what the shopper saw, and a rerun that shows whether the fixes worked. No knowledge of structured data needed.
- It catches two kinds of problems: a store an agent can't use (prices in images, unclear buttons, blocked checkout), and a purchase whose records disagree (captured but pending, paid after a decline, duplicated on retry).
- As more purchases go through agents, a merchant needs to know whether an agent can buy from them before one tries. GhostShopper tests the storefront path and the WebMCP path against the same trace, so the merchant also sees whether the order lands correctly.
- There are no revenue claims. The live results (65 → 100 in runs 50 and 51, 49 → 100 in runs 31 and 34) are from the demo store, on the Sandbox. The mock seed pair (24 → 100) is a separate, offline demo.

## Run it locally

Every result in this README, step by step: [docs/REPRODUCE.md](docs/REPRODUCE.md).

**You need:** Python 3.11+, Node 20+ (the Docker image uses Node 22) and git. No API keys are needed for mock mode.

<table>
<tr><th>Windows (PowerShell)</th><th>macOS / Linux</th></tr>
<tr><td>

```powershell
git clone https://github.com/tropicalbee/GhostShopper.git
cd GhostShopper
powershell -ExecutionPolicy Bypass -File scripts\setup.ps1
$env:PAYPAL_MODE="mock"
.venv\Scripts\python -m uvicorn backend.app.main:app --port 8000
```

</td><td>

```bash
git clone https://github.com/tropicalbee/GhostShopper.git
cd GhostShopper
bash scripts/setup.sh
PAYPAL_MODE=mock .venv/bin/python -m uvicorn \
  backend.app.main:app --port 8000
```

</td></tr>
</table>

The setup script creates `.venv`, installs the dependencies and Chromium inside it, builds the frontend, copies `.env.example` to `.env` and runs the tests.

| Open | URL |
|---|---|
| Dashboard | `http://localhost:8000/` |
| Demo store | `http://localhost:8000/store/` |
| Flaw toggles | `http://localhost:8000/store/admin` |
| Health and mode | `http://localhost:8000/api/health` |

**Try a before/after pair (second terminal, mock mode):**

```bash
python -m backend.app.seed --with-runs          # records a flawed run and a fixed run
python -m backend.app.agent.compare --last      # prints the mock score change (24 → 100)
```

**Live run (needs the keys below):**

```bash
python -m backend.app.seed                                                    # demo state, classic flaws on
python -m backend.app.agent --llm live --flaws keep --checkout --paypal sandbox --headed
python -m backend.app.agent --llm live --flaws off --checkout --paypal sandbox --headed
python -m backend.app.agent --llm live --flaws keep --checkout --paypal sandbox --headed --vision   # with VISION_MODEL set
python -m backend.app.agent.compare --last
```

**WebMCP and catalog readiness:**

```bash
python -m backend.app.webmcp discover <url>                                    # list the page's WebMCP tools (native, CDP)
python -m backend.app.webmcp run --store demo --llm live --paypal sandbox --headed
python -m backend.app.webmcp run --store showcase --llm live --paypal sandbox --headed
python -m backend.app.webmcp compare 57 54                                     # browser run vs WebMCP run
python -m backend.app.catalog_readiness --url <store>
```

On Windows, avoid `--reload` when starting runs from the dashboard. For frontend development, run `cd frontend && npm run dev` (it proxies `/api` and `/store` to port 8000).

<details>
<summary><b>Environment variables</b> (from <code>.env.example</code>)</summary>

| Variable | Needed for | Purpose |
|---|---|---|
| `PAYPAL_CLIENT_ID`, `PAYPAL_CLIENT_SECRET` | sandbox runs | Sandbox REST app, linked to a US business sandbox account |
| `PAYPAL_MODE` | optional | `sandbox` (default) or `mock` |
| `PAYPAL_VAULT_TOKEN_ID`, `PAYPAL_VAULT_CUSTOMER_ID` | optional | Saved sandbox buyer for hosted real-sandbox runs (from `python -m backend.app.vault setup/finish` on your machine). With it, real runs pay with no popup. |
| `SANDBOX_BUYER_EMAIL`, `SANDBOX_BUYER_PASSWORD` | sandbox runs | The sandbox buyer the agent logs in as. Never logged or stored. |
| `LLM_PROVIDER`, `LLM_MODEL`, `LLM_API_KEY` | live model runs | For Nemotron: `nvidia`, a tool-calling Nemotron model id, a key from build.nvidia.com |
| `LLM_BASE_URL` | optional | Overrides the provider URL. Required for `openai-compatible`. |
| `VISION_MODEL` | optional | A vision-capable model on the same provider and key as the main LLM. It turns on `look_at_page`. Without it vision is unavailable. |
| `BROWSER_PROVIDER`, `KERNEL_API_KEY` | hosted browser | `local` (default) or `kernel`. Kernel needs the store on a public URL. |
| `CHANNEL3_API_KEY` | optional | Live market check. Without it, recorded fixtures are used and labelled. |
| `DATABASE_PATH` | optional | SQLite file, default `data/ghostshopper.db` |
| `APP_BASE_URL` | optional | Public base URL, default `http://localhost:8000` |
| `PLAYWRIGHT_CHANNEL` | optional | Browser channel, such as `chromium` or `msedge` |
| `DEV_OPTIONS`, `DEMO_ADMIN_TOKEN` | optional | Developer options and the flaw toggle lock for deployed servers |
| `RETENTION_DAYS`, `TRUSTED_PROXY_HOPS` | optional | Data retention (default 30 days) and proxy hops (default 1) |
| `ALLOW_PRIVATE_URLS` | optional | `1` lets pasted store URLs point at private or local addresses. Default: on only when `APP_BASE_URL` is localhost. Keep it off on a public server. |
| `EXAMPLE_RUNS` | optional | `1` loads the bundled example checks at startup (on for the hosted demo) |
| `RUN_DAILY_CAP`, `MARKET_DAILY_CAP`, `ORDER_DAILY_CAP`, `CATALOG_DAILY_CAP` | optional | Daily caps, defaults 40, 100, 100 and 100 |

</details>

<details>
<summary><b>API</b></summary>

`POST /api/runs` (`vision: true` when the server has `VISION_MODEL`) · `GET /api/runs` · `GET /api/runs/{id}` · `GET /api/runs/{id}/compare` · `GET /api/runs/{id}/compare-path` · `GET /api/catalog` · `POST /store/webmcp/rpc` · `DELETE /api/runs/{id}` · `POST /api/runs/{id}/explain` · `GET /api/market/{sku}` · `GET /api/paypal/orders/{id}/verify`

Each browser sees only its own checks, plus the shared examples from the CLI and the seed command. The hosted site renumbers the bundled example checks: real runs 31 (49/100) and 34 (100/100) appear there as checks 1 and 2.

</details>

## Limits and FAQ

| Question | Answer |
|---|---|
| **Does it test WebMCP?** | It runs a purchase through WebMCP tools and checks the result against the purchase trace, with an 8-item tool checklist. On Fernhill the tools are our adapter for the same `shopping.*` contract PayPal's showcase registers, not PayPal's own service. On PayPal's showcase it uses PayPal's real tools as an external demo. See [PayPal's WebMCP post](https://developer.paypal.com/community/blog/WebMCP_PayPal_Agent_Ready) and [docs/research/paypal-webmcp.md](docs/research/paypal-webmcp.md). |
| **Is it an Agent Ready, ACP or UCP test?** | No. It is not a conformance test or a PayPal certification. |
| **Is the WebMCP path scored?** | No. The tool checklist is computed by code and is not a score. The readiness score rates the page path. |
| **Is 100/100 a PayPal certification?** | No. It means GhostShopper's checks found nothing wrong. It is not an Agent Ready eligibility check. |
| **Does the full trace work on any store?** | Only on the demo store. Real stores don't expose their order records, so on a live store the store order shows as unknown. |
| **Is this real money?** | No. PayPal Sandbox only, and Sandbox behaviour is not production behaviour. |
| **Where does market data come from?** | Channel3, as market context (similar listings, a median price), not reliable price intelligence. On the hosted site, a live check on 2026-11-12 found 18 similar mugs with a median of $20.13, so our $24.00 was 19.3% above it. Without a key, recorded responses are used and labelled as sample data. |
| **Can I run a real Sandbox purchase on the hosted demo?** | Any visitor can start one, bounded by daily caps, and New check picks the real sandbox by default. The presenter token only unlocks the store's flaw toggles. A completed hosted purchase is not recorded yet: hosted run 5 (2026-11-12) timed out at PayPal's password step after 120 s and captured no order. Every completed purchase so far ran locally. <!-- HOSTED_VAULT_RUN --> |
| **Does the hosted version always have a browser?** | Hosted runs depend on the Kernel configuration and quota. Hosted run 5 did run in Kernel and finished the shopping half of the flow (see the Kernel row above). |
| **Do the benchmarks prove it works on other stores?** | No. They compare the detectors with labels written for the demo store. The Shopify runs are the only check on a third-party store. |

## Credits

**Made by [tropicalbee](https://github.com/tropicalbee).** Product idea, system design, architecture decisions and validation: every live run, metric and claim in this README was checked by hand.

Coding buddy: [Claude](https://www.anthropic.com/claude) by Anthropic, who wrote the code to that design. Every change went through review before it landed.

Built for the PayPal AI Hackathon 2026, Nov 5 to 12. MIT licensed, see [LICENSE](LICENSE).

Docs: [PRD](docs/PRD.md) · [TRD](docs/TRD.md) · [Schema](docs/SCHEMA.md) · [App flow](docs/APPFLOW.md) · [Decisions](docs/DECISIONS.md) · [Metrics](docs/METRICS.md) · [Changelog](docs/CHANGELOG.md)
