# 7-day plan

Deadline Nov 12, 12:00pm PT. We aim to submit on Nov 11.

## D1 (Nov 5): repo, store, sandbox checkout
- [x] CLAUDE.md brief, MIT LICENSE, .gitignore, .env.example
- [x] Day 1 docs (PRD, TRD, SCHEMA, APPFLOW, PLAN, principles, PROGRESS, issues-and-fixes)
- [x] Scaffold store/, backend/, frontend/
- [x] Look up the current PayPal JS SDK (v6) and Orders v2 docs
- [x] Demo store: 4 products, 4 flaws behind toggles, admin toggle page and JSON API
- [x] PayPal v6 button on the checkout page
- [x] FastAPI health, create-order, capture-order (Orders v2 sandbox), orders saved to SQLite
- [x] Tests for the API and store toggles
- [ ] Manual sandbox purchase with the test buyer (needs .env credentials; user)
- [x] git init and first commits (user)

## D2 (Nov 6, done early on Nov 5): shopper agent navigation and failure logging
- [x] runs / steps / checks (+ failures view) / scores tables
- [x] Browser tools on local Playwright (open_page, find_elements, read_text, click, fill_form, take_screenshot, finish)
- [x] Tool-calling loop with a step limit; Groq adapter, replay (mock) LLM, recorder
- [x] Deterministic detectors for the 4 flaws, with evidence and screenshots
- [x] Deterministic scoring module and tests (pulled forward from D5)
- [x] POST /api/runs, GET /api/runs, GET /api/runs/{id}
- [x] Runs with all flaws on and off recorded in METRICS.md (mock LLM)
- [x] Robustness: step limit, loop detection, per-step and LLM timeouts, gave-up as a scored check
- [ ] The same two runs with live Groq (needs GROQ_API_KEY and GROQ_MODEL; user)

## D3 (Nov 7, built with mocks on Nov 5): agent completes checkout
- [x] pay_with_paypal: PayPal popup, buyer login, approve (live selectors unverified)
- [x] Buyer credentials only from SANDBOX_BUYER_EMAIL/PASSWORD; redacted, never screenshotted
- [x] Capture confirmed through the backend; order linked to the run
- [x] Checkout failures as scored checks (button, popup, approval timeout, capture)
- [x] PAYPAL_MODE=mock: fake Orders client, mock SDK and popup with failure scenarios
- [x] Human-approval fallback for CAPTCHA, verification and unknown PayPal pages (tested on the mock popup)
- [x] Mock: the fixed store buys and scores 100; the bad store buys and scores 49 (rules .3)
- [ ] Live sandbox checkout run (user; see PROGRESS.md "How to run Day 3 live")
- [x] Kernel browser behind the same tool layer (tested locally over CDP; live run needs a key and a public URL)

## D4 (Nov 8, built with mocks on Nov 5): Channel3 and verification
- [x] Research notes in docs/research/ (Channel3, Kernel)
- [x] Channel3 market check behind an interface, with recorded fixtures and a live switch
- [x] Verification: order, capture, advertised amount, currency, capture id, fees (net = gross - fee) as a scored check
- [x] Scoring by cause: only store-caused failures cost points; the rest shows as "not the store's fault"
- [x] Before/after comparison: endpoint and CLI
- [x] Deterministic fix per failure type; LLM may only reword it (cassette for now)
- [ ] Live Channel3 run (needs CHANNEL3_API_KEY; user)

## D5 (Nov 9): scoring and dashboard
- [x] Deterministic score function, unit tests, rules_version
- [x] LLM fix explanations (text only, never scored)
- [x] UI_SPEC.md (rewritten for shopkeepers and judges, shadcn style)
- [x] Real-world behaviour: any store link, browse-only live stores, robots.txt and rate limit, bot checks reported as not the store's fault
- [x] Platform detection (Shopify, Wix, WooCommerce) and plain-English fixes with platform steps
- [x] "Send to my developer" summary, plain step feed, screenshot endpoint
- [x] Dashboard design agreed with the user (light monochrome bento, shadcn, Recharts)
- [x] Dashboard built: Home, Live check, Results, Before/after, Advanced (AG Grid Community)
- [ ] Impeccable critique and polish pass on the built dashboard
- [x] Checks private per browser, per-store before and after, hardening for a public server
- [ ] Decide how live-store payment checks count (default in code: excluded)

## Evaluation (added Nov 5, between D4 and D5)
- [x] Saboteur: 6 more flaws (10 in total), each a toggle with a ground-truth label
- [x] Benchmark: precision, recall and missed flaws per type; classic 16-combination matrix and 30 random combinations
- [x] LLM-as-judge for fix explanations (secondary metric; harness tested on cassettes only)
- [ ] Judge and saboteur proposals with live Groq (user)

## D6 (Nov 10): deploy and README
- [x] Serve the frontend build from FastAPI
- [x] Prep: setup scripts, Dockerfile, .dockerignore, render.yaml, GitHub Actions workflow
- [x] README draft: problem, audience, how it works, setup, run, tools, built-during-hackathon
- [ ] Render free tier deploy, env vars set, sandbox purchase on the hosted URL
- [ ] Hosted URL in the README
- [ ] Fresh-clone test

## D7 (Nov 11): video and submit
- [x] docs/VIDEO_SCRIPT.md (3 minutes) and seed command for the demo state
- [ ] Record the demo video (under 3 minutes)
- [ ] Devpost description, with the built-during-the-hackathon section from CHANGELOG.md
- [ ] Submit
