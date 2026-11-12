# Changelog

Everything below was built during the PayPal AI Hackathon 2026.

## 2026-11-12 (final audit fixes)
- `/api/catalog` has a total time bound and a daily cap (`CATALOG_DAILY_CAP`, default 100). `look_at_page` is capped at 5 per run.
- The stuck PayPal popup screenshot is saved as `screenshot`, so the scorecard shows it, and no path is stored when the capture failed.
- `GET /orders/{id}` and `/orders/{id}/verify` validate the id like refund (400 `BAD_ORDER_ID`), and are agent-only: the server makes a random key at startup (`backend/app/internal_key.py`), in-process runs get it from memory and CLI runs from `data/.internal_key`; anyone else gets a 404.
- Only popup payments are forced into Kernel (its live view is how a person approves); saved-buyer payments use the server's `BROWSER_PROVIDER`, so a local server's real check no longer sends Kernel to an unreachable `localhost` (run 60 before, run 61 after).
- Real runs on the hosted server pay with a saved sandbox buyer from `PAYPAL_VAULT_TOKEN_ID` and `PAYPAL_VAULT_CUSTOMER_ID` (seeded at startup, `vault_ready` in health).
- Banner without hard-coded run numbers. Architecture diagram redrawn for the required model, vision, WebMCP through the browser and the saved-buyer payment; data model adds `vault_tokens`; TRD, APPFLOW and SCHEMA mermaid updated.
- `docs/REPRODUCE.md`: every README result, from the hosted demo, a local clone with no keys, or your own free sandbox keys.
- A run with no LLM configured returns 400 `RUN_CONFIG` unless developer options are on, instead of silently using the rule-based navigator.
- Localhost origins are hidden in every failure text column. A one-time log line when `X-Forwarded-For` has fewer entries than `TRUSTED_PROXY_HOPS`.
- Hosted real run 5 recorded in METRICS.md.
- Docs: PRD lists all 20 store flaws, SCHEMA has `runs.live`, `platform` and `platform_evidence`, README states what the hosted and local evidence shows.

## 2026-11-12 (final audit)
- Advanced grid hides the recorded localhost origin on example checks; `ALLOW_PRIVATE_URLS` documented; Channel3 docs match the live hosted check.

## 2026-11-12 (WebMCP and catalog readiness)
- WebMCP path: the shopper uses a page's WebMCP tools through Chromium's native WebMCP (CDP WebMCP domain), with a shim fallback. `python -m backend.app.webmcp discover | run | compare`.
- Fernhill adapter for the `shopping.*` tool contract (`store/static/webmcp.js`, `POST /store/webmcp/rpc`) on the store's own order and capture code.
- Runtime-side buyer approval and order read-back for WebMCP runs, so the five-record trace applies to both paths.
- 8 WebMCP tool checks (a checklist, not a score) and a browser vs WebMCP comparison (`GET /api/runs/{id}/compare-path`).
- PayPal's WebMCP showcase as a labelled external demo.
- Catalog readiness (`GET /api/catalog`, `python -m backend.app.catalog_readiness`), polite pacing and a minimum sample.
- `runs.path` and `runs.webmcp` columns, dashboard components for both features.
- Mobile landing menu and hero overflow fixes, link preview card, demo-store paths in the trace view, trace matrix timeout fix.
- Shopper vision: optional `look_at_page` tool (store pages only), `VISION_MODEL`, `--vision`, `vision: true` on `POST /api/runs`, a New check switch, a Vision label on runs, `vision_available` in health. It never changes the score.
- Seven live runs (53 to 59) and README, DEVPOST and docs rewritten for the WebMCP framing.

## 2026-11-12 (video v2)
- Recorder: `--bad-flaws`, new read-only tour and live safety recorders.
- Three new live Sandbox runs for the video (50, 51, 52) and a new 2:54 demo video cut to the voice.


## 2026-11-05 (Day 1)
- Project scaffold: FastAPI backend, React + Vite + TS frontend, demo store, MIT license, env template.
- Demo store "Fernhill Ceramics" with 4 products and 4 switchable flaws: price only in an image, missing structured data, ambiguous buy buttons, an extra checkout step.
- PayPal JS Web SDK v6 checkout button on the store.
- Orders v2 sandbox endpoints: create order (priced on the server) and capture (stores the capture id and PayPal's fee breakdown).
- Planning docs: PRD, TRD, schema, app flow, 7-day plan.

## 2026-11-05 (Days 2-3, ahead of schedule)
- Mystery-shopper agent: an LLM tool-calling loop driving a local Playwright browser (open, find elements, read text, click, fill forms, screenshot, finish).
- Readiness checks run by code on every page the agent sees, with evidence (selector, reason, screenshot) stored per run in SQLite.
- A 0-100 readiness score with stage sub-scores and a fix list ordered by points.
- Groq adapter over its OpenAI-compatible API, plus record and replay of LLM runs for repeatable tests.
- `pay_with_paypal`: the agent clicks the PayPal button, handles the popup, logs in as the sandbox buyer, approves, and confirms the capture. Order, capture id, amount and fees are saved with the run.
- PayPal mock mode (fake Orders API, mock SDK and popup) with failure scenarios: no button, popup blocked, approval stuck, capture declined.
- Runs API: `POST /api/runs`, `GET /api/runs`, `GET /api/runs/{id}`.

## 2026-11-05 (Days 4-7 prep, ahead of schedule)
- Scoring by cause: only problems the store causes cost points. A declined card, a blocked popup or a crashed run shows up as "not the store's fault", and the score is worked out over what the store controls.
- Human-approval fallback: when PayPal shows a CAPTCHA, a verification step or an unknown page, the run pauses as "awaiting human approval", a person finishes the PayPal window, and the run carries on to confirm the capture.
- Agent safeguards: step limit, loop detection, per-step and LLM timeouts, and giving up recorded as a scored check.
- Payment verification: order, capture, advertised price, currency and PayPal fee arithmetic all have to match.
- Market check with Channel3: similar products and whether the price is competitive (live with a key, recorded fixtures without).
- Kernel cloud browser as an alternative to local Playwright, using the same agent code.
- Before/after comparison of two runs (`GET /api/runs/compare`, `python -m backend.app.agent.compare`).
- A specific fix for every failure type; the LLM can reword fixes for merchants but can't change them.
- 6 more realistic store flaws (10 in total) and 18 checks: price changing at checkout, sold-out items still buyable, broken photo alt text, a cookie banner over the buy button, missing currency, a misleading sale price.
- Saboteur benchmark with ground-truth labels: precision and recall per flaw, over all 16 combinations of the original flaws and 30 random combinations.
- LLM-as-judge for fix explanations, kept apart from the score.
- One-command setup scripts, Dockerfile, Render blueprint, GitHub Actions workflow, README draft, video script, and a seed command for the demo.

## 2026-11-06 (Day 5: dashboard)
- Merchant dashboard in React with shadcn/ui, Recharts and AG Grid Community: paste a store link, watch the shopper's steps in plain words, get a score with the top three fixes, and send the technical report to a developer.
- Before and after screen: the score counts up from the old run to the new one, with fixed and remaining problems in plain words.
- Advanced view for judges and developers: score gauge, score across runs, points by stage, payment check with PayPal fee and net, failures table, agent steps with screenshots, market check.
- Works on phones (Simple view) and desktop (Advanced view). Practice runs, mock PayPal and sample market data are labelled on screen.
- Checks are private to the browser that ran them, with "My checks", delete, and a 30-day retention. Before and after compares your own previous check of the same store.
- The Ledger redesign: white, square and ruled, soft ink, Geist and Geist Mono, colour only for status. The shopper's path shows where an AI shopper got stuck and fills live during a check. A sidebar on desktop and a menu on phones, from 360px phones to wide screens.
- Hardening for a public server: developer options and the demo store settings locked, rate limits, security headers and CSP, server-side request forgery checks on every request, and the dashboard served by FastAPI.
- The shopper's LLM provider is configurable: Groq, OpenAI, OpenRouter, Together, Ollama, any OpenAI-compatible URL, or Anthropic, through `LLM_PROVIDER`, `LLM_MODEL`, `LLM_API_KEY` and `LLM_BASE_URL`. Adding one is a registry entry.
- Run starts can no longer race, a timed-out start is cancelled, and unclosed LLM clients are closed.
- Explain on shared example checks is refused. The demo store's settings unlock through a form and a cookie instead of a token in the URL.
- SQLite in WAL mode with a busy timeout and indexes, an in-memory cache for finished runs and market checks, a paged runs list, gzip, and per-path cache headers.
- Frontend speed: fewer re-renders while polling, My checks loads 20 at a time, skeletons for every loading region, and a meta description. Lighthouse is 100 across the board on desktop.
- Fixed the failures table's oversized and clipped rows, and flattened the dialog backdrops.

## 2026-11-06 (store redesign)
- New design for the demo store: Shopify-style layout in Montserrat, with a navbar, hero, product grid, category banners, studio section and a dark footer. It works on phones, tablets and desktop.
- 12 products in 4 categories with real local photos, a credits page, and fictional reviews with ratings.
- Minimal checkout header and step trail. A sold-out product shows a disabled button and an email link.
- The 10 flaw toggles still work. The ambiguous buttons and the price image were restyled to look like a real shop.
- Hand-made market fixtures for the 8 new SKUs, new click ids in the 5 hand-written cassettes, and related products no longer list sold-out items.
- The stylesheet URL carries a content hash so browsers pick up CSS changes.

## 2026-11-07 (live test fixes)
- Live test of the refund, budget, product feed and readiness panel against the real sandbox. The refund verified; budget and feed behaved as designed.
- The agent has more ways to find PayPal's Complete Purchase button and scrolls it into view before clicking. Needs one live confirm.
- `POST /api/runs` accepts a dev-only `headed` option so API runs can use a visible browser.
- PayPal readiness counts the button the agent actually clicked, instead of trusting a page scan that can run before the button draws.
- The Simple results view no longer overflows at phone width.

## 2026-11-07 (first real sandbox purchase)
- First real PayPal sandbox purchase by the agent: order created, approved in the popup, captured and verified (100/100).
- The agent detects PayPal's own error page, decodes the issue name from the URL and fails `payment_approved` at once with code `paypal_error_page`. It counts as environment, so the score is not hurt.
- New mock scenario `seller_login`, with tests for it and for decoding error-page URLs. 234 tests pass.
- `.env.example` notes that the buyer must be the personal sandbox account and both sandbox accounts should be US.

## 2026-11-07 (PayPal features)
- Refund round trip: the full capture is refunded through Payments v2, read back and checked (status, amount, currency). "Refund test payment" button, owner only, not scored.
- PayPal readiness panel and Advanced tab: a deterministic 0 to 100 figure for the PayPal setup on the pages the agent visited, with a checklist and links to PayPal docs. The agent-readiness score is unchanged.
- "Your money" panel: gross, fee, net, effective fee and a created, captured, refunded timeline.
- Agent budget: optional spending limit on the API, the CLI (`--budget`) and Home. Enforced in code before the PayPal button is clicked; going over records `over_budget`.
- Product feed in Google product feed columns, with coverage, fixes and a CSV download. Nothing is submitted to Store Sync.
- PayPal button timeout raised from 20 s to 30 s.
- 287 tests pass.

## 2026-11-08 (blockers and audit fixes)
- The hosted app can run a real sandbox purchase on request. A run opts in with a checkbox on Home. The server refuses it with a clear message when the PayPal, Kernel or buyer settings are missing. Mock PayPal stays the default.
- The Live screen links to the shopper's browser when a person needs to finish a PayPal step.
- Four new store flaws for PayPal readiness: no PayPal Express, no Pay Later, no Venmo and no card checkout.
- PayPal v6 component names checked against PayPal's docs and corrected.
- The budget is checked against the amount the store charges, before anything is approved.
- Fixes from a security and production review of the PayPal features: refund error handling, a crash on oversized budgets and refund id checks.

## 2026-11-09 (money first, vault payment)
- The LLM can no longer fill password fields on any store.
- Docs name NVIDIA Nemotron as the primary LLM, with Groq as an alternative. The provider is set in `.env`.
- The results screen leads with money: lost sale, captured payment with fee and net, or paid but at risk. Mock runs are labelled practice mode. PayPal readiness sits right under it.
- New store flaw `no_guest_checkout`: an account wall with no PayPal button. It fails the PayPal button check with `account_required`.
- Vault agent payment: `python -m backend.app.vault setup`, then `--payment vault` pays with the buyer's saved PayPal account through `POST /api/paypal/agent-orders`, with no popup or password. A deployed sandbox payment needs the presenter unlock.

## 2026-11-10 (purchase trace, safety guard, redesign)
- Purchase trace: five records of one purchase (what the agent wanted, the store's order, PayPal's order, PayPal's capture, what the store says) compared field by field, with the first mismatch explained. Unknown values stay unknown. It doesn't change the score.
- The demo store keeps its own orders and an order page. The shopper reads that page back after payment.
- Four store flaws for purchase bugs: never marks paid, declined marked paid, success after cancel, duplicate on retry. The mock PayPal gained `buyer_cancels` and `first_attempt_fails`, and the agent retries once on a temporary capture error.
- Prompt-injection guard: page content is framed as data, hard limits (no other hosts, no downloads, no password or card fields), a detector for text aimed at AI agents, an agent-safety report on each run and a `hidden_agent_instructions` flaw. It doesn't change the score.
- Frontend redesign in a black monochrome receipt style: Landing, New check, Live and Results with the trace and the safety panel.
- Architecture, sequence, trace and data-model diagrams in `docs/diagrams/`, with Mermaid versions in the docs.
- Trace benchmark: `python -m backend.app.eval benchmark --matrix trace` runs 33 hand-labelled scenarios (store flaw by PayPal outcome, plus tampered ids) against the purchase trace. The first run got 31 of 32; a store that lost PayPal's order id is now flagged as paid without a PayPal reference, with PayPal's records unknown, and all 33 pass.

## 2026-11-11 (live runs, ID links, Kernel fix)
- Live runs with Nemotron on the real PayPal sandbox: bad store 49/100 and purchased, fixed store 100/100, cassettes recorded. A Shopify demo store browse run scored 62/100 locally and in Kernel.
- Trace checks the four ID links between the store order, PayPal order and capture. Broken links come first, and a paid order with no PayPal id leaves PayPal's side unknown.
- The store order is created before the PayPal order and sent as `custom_id`. The capture id is saved on it.
- Kernel runs no longer hang on sites with service workers. Sessions are always deleted, and live and Kernel runs stop at 600 s.
- `LLM_PROVIDER=nvidia`, and "not tested" reasons that say what actually happened.
- Tests never use Kernel or paid API keys from `.env`.
- Frontend: a "Linked by ID" section under the trace, a ghost with a shopping bag as logo and favicon, and the ghost walks the landing page stepper to the first mismatch.
- Security pass before the deploy: rate limits read X-Forwarded-For from the right, shared daily caps with a presenter bypass, a locked mock PayPal switch, capped and DNS-pinned store fetches, a throttled admin unlock with a hashed cookie, and a non-root pinned Docker image.
- Pitch pass on the README, PRD and video script, plus a Devpost description (docs/DEVPOST.md).
- Market check drops duplicate listings (same title on the same domain) and multi-packs or sets from the comparison and the median, and the report says how many were removed.
- The detailed architecture diagram now has one number per step, no crossing lines, and lettered side requests for the market check (A) and fix wording (B).

- README rewritten for judges and developers: demo screenshots, technical depth, benchmarks split into mock and real Sandbox, setup for Windows and macOS/Linux, limits and FAQ, plus a banner at docs/assets/banner.svg.
- README rewritten around the PayPal pitch, with a new banner, today's run screenshots, results split into live and mock, setup per OS and credits.

## 2026-11-12 (video day)
- Remotion edit of the demo video in `video/`: animated title, score and end cards, zooms, per-row voice clips and music. The first take had kinetic captions; the final v2 cut has none.
- Sharper recordings from a CDP screencast, with zoom targets saved per scene.
- PayPal popup: unknown pages get a grace period before a human is asked, with a screenshot as evidence.
- `payment: "vault"` on `POST /api/runs` (dev option).
