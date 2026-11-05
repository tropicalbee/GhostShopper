# Progress

## 2026-11-05 (Day 2 + Day 3, autonomous session)

**Done: Day 2**
- Shopper agent as a real tool-calling loop on local Playwright: `open_page`, `find_elements`, `read_text`, `click`, `fill_form`, `take_screenshot`, `finish`. CLI `python -m backend.app.agent` and `POST/GET /api/runs`.
- Every step (tool, args, observation, URL, screenshot, timing) and every check outcome (reason, selector, screenshot) in SQLite (`runs`, `steps`, `checks` + `failures` view, `scores`).
- Deterministic detectors for all 4 flaws plus product found / checkout reached. Deterministic score (`backend/app/scoring.py`, rules `2026-11-05.1`), built test-first.
- Runs: flaws ON -> 20/100 (14 steps, 5 failures); flaws OFF -> 80/100 (8 steps, 0 failures; payment not part of Day 2). See METRICS.md.
- **LLM is mocked**: `GROQ_API_KEY`/`GROQ_MODEL` are not set (per `/api/health` `groq_configured: false`), so runs replay hand-recorded cassettes (`backend/app/agent/cassettes/`). The loop, browser, detectors and score are all real. Switch to live with `--llm groq` (add `--record <name>` to save the live run as a new cassette).

**Done: Day 3 (mocks only, no live PayPal attempted)**
- `pay_with_paypal` tool: PayPal button -> popup -> buyer login -> approve -> capture confirmed via `GET /api/paypal/orders/{id}` -> order linked to the run.
- Buyer credentials only from `SANDBOX_BUYER_EMAIL` / `SANDBOX_BUYER_PASSWORD`; never shown to the LLM, redacted before every DB write, popup screenshotted only before typing. Tested.
- Checkout failures are scored checks: `paypal_button_found`, `popup_opened`, `payment_approved` (approval timeout), `capture_completed`.
- `PAYPAL_MODE=mock` server: fake Orders client + mock v6 SDK/popup, scenarios `no_button`, `popup_blocked`, `approval_stuck`, `capture_declined`. Live sandbox is the default and refuses to run without all credentials.
- Mock runs: bad store buys but scores 40; fixed store buys and scores 100; capture declined scores 95 with the failure logged.
- Tests: 64 passing (unit + browser end-to-end).

**In progress**
- Nothing open in code.

**Next (Day 4)**
- Live checks below (user), then Channel3 market check + order/fee verification. Kernel browser factory if time.

**Blockers / needs the user**
- No Groq key/model configured: live LLM runs not done.
- Live PayPal sandbox checkout not run (by instruction). The sandbox popup selectors in `agent/paypal_flow.py` (`SELECTORS`) are unverified.
- Not a git repo yet; commits are prepared below in the session summary.

### How to run Day 3 live (when you're back)

1. **`.env`** (you edit it; the agent never does): `PAYPAL_CLIENT_ID`, `PAYPAL_CLIENT_SECRET` (sandbox REST app), `PAYPAL_MODE=sandbox` (or leave unset), `SANDBOX_BUYER_EMAIL`, `SANDBOX_BUYER_PASSWORD` (sandbox **personal** account). For live LLM also `GROQ_API_KEY` and `GROQ_MODEL` (e.g. `openai/gpt-oss-120b` or `llama-3.3-70b-versatile`; check console.groq.com/docs/models).
2. **Install** (once): `.venv\Scripts\python -m pip install -r backend/requirements-dev.txt`, then `$env:PLAYWRIGHT_BROWSERS_PATH="0"; .venv\Scripts\python -m playwright install chromium`.
3. **Start the server** (without `--reload`: on Windows uvicorn's reload mode switches to an event loop that cannot start Playwright's browser process for `/api/runs`; not tested, the CLI is unaffected):
   `.venv\Scripts\python -m uvicorn backend.app.main:app --port 8000`
   `http://localhost:8000/api/health` must show `"paypal_mode": "sandbox", "paypal_configured": true`.
4. **Manual purchase first** (Day 1 steps) to prove the credentials work.
5. **Agent, live PayPal, mock LLM, browser visible** (second terminal):
   `.venv\Scripts\python -m backend.app.agent --llm mock --cassette day3_checkout_flaws_off --flaws off --checkout --paypal sandbox --headed`
   Expect `outcome=purchased`, score 100, and an `order:` line with real capture id and PayPal fee.
6. **If a payment check fails**: the reason names the stuck stage (e.g. `stuck waiting for approve`). Look at `runs/run-<id>/paypal-popup-before-login.png` and `check-<key>.png`, then adjust `SELECTORS` in `backend/app/agent/paypal_flow.py`. Live timeouts are in `LIVE_TIMEOUTS`.
7. **Bad store, live PayPal**: same command with `--cassette day3_checkout_flaws_on --flaws on`. Expect a purchase and score 40.
8. **Live Groq** (optional): `--llm groq --record live_off_1 --flaws off --checkout --paypal sandbox`, then `--flaws on --record live_on_1`. The recorded cassettes can be replayed later with `--llm mock --cassette live_off_1`.
9. Check the payment in the sandbox merchant account, then send me the CLI output (or add it to METRICS.md).

---

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
