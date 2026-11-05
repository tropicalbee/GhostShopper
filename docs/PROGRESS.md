# Progress

## 2026-11-05 (Day 1)

**Done**
- Repo scaffold: `store/`, `backend/`, `frontend/`, MIT LICENSE, `.gitignore`, `.env.example`, CLAUDE.md, Day 1 docs.
- PayPal research: JS Web SDK v6 (`/web-sdk/v6/core`) + Orders v2. Notes in `docs/research/paypal.md`.
- Demo store "Fernhill Ceramics": 4 products (1 sold out), product/checkout/thanks pages, PayPal v6 button. 4 flaws behind toggles (default ON) at `/store/admin` and `PUT /store/admin/flaws.json`.
- Backend: `GET /api/health`, `POST /api/paypal/orders`, `POST /api/paypal/orders/{id}/capture`, `GET /api/paypal/orders/{id}`. Orders + capture fees stored in SQLite.
- Frontend: Vite + React + TS placeholder that reads `/api/health`. Builds clean.
- Tests: 23 passing (API + store toggles). Live smoke test of all store pages and the explicit "PayPal not configured" errors.

**In progress**
- Manual sandbox purchase: code is ready, needs `PAYPAL_CLIENT_ID` / `PAYPAL_CLIENT_SECRET` in `.env` (user).

**Next (Day 2)**
- runs / steps / failures tables, Playwright tool layer, Groq tool-calling loop, deterministic flaw detectors.

**Blockers**
- No sandbox credentials in `.env` yet, so no real PayPal call has been made.
- Not a git repo yet; user to `git init` and commit (agent does not run git writes).
