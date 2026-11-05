# 7-day plan

Deadline Nov 12, 12:00pm PT. Target submit Nov 11.

## D1 (Nov 5): repo + store + sandbox checkout
- [x] CLAUDE.md brief, MIT LICENSE, .gitignore, .env.example
- [x] Day 1 docs (PRD, TRD, SCHEMA, APPFLOW, PLAN, principles, PROGRESS, issues-and-fixes)
- [x] Scaffold store/, backend/, frontend/
- [x] Look up current PayPal JS SDK (v6) and Orders v2 docs
- [x] Demo store: 4 products, 4 flaws behind toggles, admin toggle page + JSON API
- [x] PayPal v6 button on checkout page
- [x] FastAPI health, create-order, capture-order (Orders v2 sandbox), orders saved to SQLite
- [x] Tests for API and store toggles
- [ ] Manual sandbox purchase with test buyer verified (needs .env credentials; user step)
- [ ] git init + first commits (user step)

## D2 (Nov 6, done early on Nov 5): shopper agent navigation + failure logging
- [x] runs / steps / checks (+ failures view) / scores tables
- [x] Browser tool layer on local Playwright (open_page, find_elements, read_text, click, fill_form, take_screenshot, finish)
- [x] Tool-calling loop with step limit; Groq adapter + replay (mock) LLM + recorder
- [x] Deterministic detectors for the 4 flaws, with evidence + screenshots
- [x] Deterministic scoring module + tests (started early from D5)
- [x] POST /api/runs, GET /api/runs, GET /api/runs/{id}
- [x] Runs with all flaws ON and OFF recorded in METRICS.md (mock LLM)
- [ ] Same two runs with live Groq (needs GROQ_API_KEY + GROQ_MODEL; user)

## D3 (Nov 7, built with mocks on Nov 5): agent completes checkout
- [x] pay_with_paypal tool: PayPal popup + buyer login + approve (live selectors unverified)
- [x] Buyer credentials only from SANDBOX_BUYER_EMAIL/PASSWORD; redacted, never screenshotted
- [x] Capture confirmed via backend; order linked to run (orders.run_id, runs.order_id)
- [x] Checkout failures as scored checks (button, popup, approval timeout, capture)
- [x] PAYPAL_MODE=mock: fake Orders client + mock SDK/popup with failure scenarios
- [x] Mock: fixed store buys and scores 100; bad store buys and scores 40
- [ ] Live sandbox checkout run (user; see PROGRESS.md "How to run Day 3 live")
- [ ] Kernel browser factory behind the same tool layer (moved to D4 if time; local Playwright is enough for dev)

## D4 (Nov 8): Channel3 + verification
- [ ] Research note in docs/research/ (Channel3, Kernel)
- [ ] Channel3 market check for the target product
- [ ] Verification: order status, capture COMPLETED, amount = catalog price x qty, fees present, net = gross - fee

## D5 (Nov 9): scoring + dashboard
- [x] Deterministic score function + unit tests, rules_version (done D2)
- [ ] UI_SPEC.md
- [ ] Dashboard: run button, score, failures grid (AG Grid Community), fix list, verification, run comparison
- [ ] LLM fix explanations (text only)

## D6 (Nov 10): deploy + README
- [ ] Serve frontend build from FastAPI
- [ ] Render free tier deploy, env vars set, sandbox purchase on hosted URL
- [ ] README: problem, audience, setup, hosted URL, tools used
- [ ] Fresh-clone test

## D7 (Nov 11): video + submit
- [ ] Demo video under 3 min (bad -> run -> fix -> rerun -> purchase)
- [ ] Devpost description, "built during the hackathon" from CHANGELOG.md
- [ ] Submit
