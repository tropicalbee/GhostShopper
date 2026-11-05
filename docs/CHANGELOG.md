# Changelog

Everything below was built during the PayPal AI Hackathon 2026.

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
