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

## D2 (Nov 6): shopper agent navigation + failure logging
- [ ] runs / steps / failures tables
- [ ] Browser tool layer on local Playwright (read_page, navigate, click, fill, select, finish)
- [ ] Groq tool-calling loop with step limit and timeout
- [ ] Deterministic detectors for the 4 flaws, with evidence + screenshots
- [ ] POST /api/runs, GET /api/runs/{id} (steps, failures)
- [ ] Record first numbers in METRICS.md

## D3 (Nov 7): agent completes checkout
- [ ] pay_with_paypal tool: PayPal popup + sandbox buyer login + approve
- [ ] Link orders.run_id
- [ ] Agent buys successfully on the fixed store; fails with evidence on the bad store
- [ ] Kernel browser factory behind the same tool layer

## D4 (Nov 8): Channel3 + verification
- [ ] Research note in docs/research/ (Channel3, Kernel)
- [ ] Channel3 market check for the target product
- [ ] Verification: order status, capture COMPLETED, amount = catalog price x qty, fees present, net = gross - fee

## D5 (Nov 9): scoring + dashboard
- [ ] Deterministic score function + unit tests, rules_version
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
