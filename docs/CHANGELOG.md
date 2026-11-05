# Changelog

All work below was built during the PayPal AI Hackathon 2026.

## 2026-11-05 (Day 1)
- Project scaffold (FastAPI backend, React + Vite + TS frontend, demo store), MIT license, env template.
- Demo store "Fernhill Ceramics" with 4 products and 4 toggleable agent-readiness flaws: price only in an image, missing structured data, ambiguous buy buttons, extra checkout step.
- PayPal JS Web SDK v6 checkout button on the store.
- Orders v2 sandbox endpoints: create order (server-side pricing) and capture (stores capture id and PayPal fee breakdown).
- Planning docs: PRD, TRD, schema, app flow, 7-day plan.

## 2026-11-05 (Days 2-3, built ahead of schedule)
- Mystery-shopper agent: a real LLM tool-calling loop driving a local Playwright browser (open, find elements, read text, click, fill forms, screenshot, finish).
- Deterministic agent-readiness checks on every page the agent sees, with evidence (selector, reason, screenshot), stored per run in SQLite.
- Deterministic 0-100 readiness score with stage sub-scores and a prioritized fix list.
- Groq (OpenAI-compatible) LLM adapter, plus replay/record of LLM runs for reproducible tests.
- `pay_with_paypal`: agent clicks the PayPal button, handles the popup, logs in as the sandbox buyer, approves, and confirms the capture with order, capture id, amount and fees recorded against the run.
- PayPal mock mode (fake Orders API + mock SDK and popup) with failure scenarios: no button, popup blocked, approval stuck, capture declined.
- Runs API: `POST /api/runs`, `GET /api/runs`, `GET /api/runs/{id}`.
