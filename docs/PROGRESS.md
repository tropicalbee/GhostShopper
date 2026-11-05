# Progress

## 2026-11-05 (tasks 1-11, second autonomous session)

### Done
- Scoring by cause. Every failure has a code, and the code says whether the store caused it. Only store-caused failures cost points. The rest, plus any checks they blocked, are excluded and listed as "not the store's fault", and the score is worked out over what's left. A declined card now scores 100, judged on 85 points, and the scorecard explains it. The rubric is in TRD.md and the reasoning for each weight is in DECISIONS.md.
- Human-approval fallback. A CAPTCHA, a verification step or an unknown PayPal page pauses the run as `awaiting_human`. A person finishes the PayPal window, and the run continues and confirms the capture. Tested with the mock popup, both with a simulated person and with nobody there.
- Robustness: step limit, loop detection, per-step and LLM timeouts, and giving up recorded as a scored check (task_completed). The outcome now comes from the checks; what the LLM claims is kept but never used.
- Verification of order, capture, advertised price, currency and fee arithmetic, as the scored check payment_verified.
- Market check behind an interface, with recorded fixtures for all four products (labelled as such) that switch to live Channel3 once `CHANNEL3_API_KEY` is set.
- Kernel as a browser provider, using the same agent code. It runs on Kernel's REST API plus CDP and was tested locally with Chromium standing in for Kernel's browser.
- Before/after comparison: `GET /api/runs/compare` and `python -m backend.app.agent.compare --last`.
- A fix for every failure type, and LLM rewording of fixes (cassette for now).
- Saboteur: 6 new flaws (10 in total), each a toggle with a ground-truth label, plus a scripted navigator and a benchmark. Precision and recall were 1.0 on the 16-combination classic matrix and on 30 random combinations. LLM flaw ideas are saved but don't count until implemented.
- LLM-as-judge for fix explanations, in its own table and never part of the score. It's only been tested on a cassette.
- Day 6 prep: setup scripts (PowerShell and bash), Dockerfile, `.dockerignore`, `render.yaml`, GitHub Actions workflow, README draft.
- Demo prep: `docs/VIDEO_SCRIPT.md` and `python -m backend.app.seed` (`--with-runs` records a backup before/after pair: 49 to 100).
- Tests: 142 passing. The docs were rewritten in plain language.

### Mocked
- The LLM: replayed cassettes for runs, fix rewording, the judge and flaw ideas. Benchmarks used the scripted navigator, which isn't an LLM.
- PayPal: `PAYPAL_MODE=mock` for every checkout run so far. No live PayPal login or payment has happened.
- Channel3: recorded fixtures. Kernel: a local stand-in only.

### Next
- Day 5: UI_SPEC.md, then the dashboard. I haven't started either, as instructed.

### Needs you, most important first
1. Run Day 3 live (steps below). It's the only way to check the PayPal popup selectors (`SELECTORS` in `backend/app/agent/paypal_flow.py`), and the demo depends on it.
2. Put `GROQ_API_KEY` and `GROQ_MODEL` in `.env`, then rerun the before/after pair with `--llm groq --record <name>`. We have no live agent behaviour yet, and the judge numbers aren't valid until it runs live.
3. Commit this session's work (commands are in the session summary).
4. Optional: `KERNEL_API_KEY` for a Kernel run (it needs a public store URL, so effectively after the Render deploy) and `CHANNEL3_API_KEY` for a live market check.
5. Check the GitHub Actions versions in `.github/workflows/tests.yml` before the first push.

### How to run Day 3 live (when you're back)

The steps below still apply. Two notes: the summary now shows the scorecard, including a "not the store's fault" section, and if PayPal shows a verification step in a headed run, finish it in the PayPal window and the run carries on.

## 2026-11-05 (Day 2 + Day 3, autonomous session)

Done: Day 2
- Shopper agent as a real tool-calling loop on local Playwright: `open_page`, `find_elements`, `read_text`, `click`, `fill_form`, `take_screenshot`, `finish`. CLI `python -m backend.app.agent` and `POST/GET /api/runs`.
- Every step (tool, args, observation, URL, screenshot, timing) and every check outcome (reason, selector, screenshot) in SQLite (`runs`, `steps`, `checks` + `failures` view, `scores`).
- Deterministic detectors for all 4 flaws plus product found / checkout reached. Deterministic score (`backend/app/scoring.py`, rules `2026-11-05.1`), built test-first.
- Runs: flaws ON -> 20/100 (14 steps, 5 failures); flaws OFF -> 80/100 (8 steps, 0 failures; payment not part of Day 2). See METRICS.md.
- LLM is mocked: `GROQ_API_KEY`/`GROQ_MODEL` are not set (per `/api/health` `groq_configured: false`), so runs replay hand-recorded cassettes (`backend/app/agent/cassettes/`). The loop, browser, detectors and score are all real. Switch to live with `--llm groq` (add `--record <name>` to save the live run as a new cassette).

Done: Day 3 (mocks only, no live PayPal attempted)
- `pay_with_paypal` tool: PayPal button -> popup -> buyer login -> approve -> capture confirmed via `GET /api/paypal/orders/{id}` -> order linked to the run.
- Buyer credentials only from `SANDBOX_BUYER_EMAIL` / `SANDBOX_BUYER_PASSWORD`; never shown to the LLM, redacted before every DB write, popup screenshotted only before typing. Tested.
- Checkout failures are scored checks: `paypal_button_found`, `popup_opened`, `payment_approved` (approval timeout), `capture_completed`.
- `PAYPAL_MODE=mock` server: fake Orders client + mock v6 SDK/popup, scenarios `no_button`, `popup_blocked`, `approval_stuck`, `capture_declined`. Live sandbox is the default and refuses to run without all credentials.
- Mock runs: bad store buys but scores 40; fixed store buys and scores 100; capture declined scores 95 with the failure logged.
- Tests: 64 passing (unit + browser end-to-end).

In progress
- Nothing open in code.

Next (Day 4)
- Live checks below (user), then Channel3 market check + order/fee verification. Kernel browser factory if time.

Blockers / needs the user
- No Groq key/model configured: live LLM runs not done.
- Live PayPal sandbox checkout not run (by instruction). The sandbox popup selectors in `agent/paypal_flow.py` (`SELECTORS`) are unverified.
- Not a git repo yet; commits are prepared below in the session summary.

### How to run Day 3 live (when you're back)

1. `.env` (you edit it; the agent never does): `PAYPAL_CLIENT_ID`, `PAYPAL_CLIENT_SECRET` (sandbox REST app), `PAYPAL_MODE=sandbox` (or leave unset), `SANDBOX_BUYER_EMAIL`, `SANDBOX_BUYER_PASSWORD` (sandbox personal account). For live LLM also `GROQ_API_KEY` and `GROQ_MODEL` (e.g. `openai/gpt-oss-120b` or `llama-3.3-70b-versatile`; check console.groq.com/docs/models).
2. Install (once): `.venv\Scripts\python -m pip install -r backend/requirements-dev.txt`, then `$env:PLAYWRIGHT_BROWSERS_PATH="0"; .venv\Scripts\python -m playwright install chromium`.
3. Start the server (without `--reload`: on Windows uvicorn's reload mode switches to an event loop that cannot start Playwright's browser process for `/api/runs`; not tested, the CLI is unaffected):
   `.venv\Scripts\python -m uvicorn backend.app.main:app --port 8000`
   `http://localhost:8000/api/health` must show `"paypal_mode": "sandbox", "paypal_configured": true`.
4. Manual purchase first (Day 1 steps) to prove the credentials work.
5. Agent, live PayPal, mock LLM, browser visible (second terminal):
   `.venv\Scripts\python -m backend.app.agent --llm mock --cassette day3_checkout_flaws_off --flaws off --checkout --paypal sandbox --headed`
   Expect `outcome=purchased`, score 100, and an `order:` line with real capture id and PayPal fee.
6. If a payment check fails: the reason names the stuck stage (e.g. `stuck waiting for approve`). Look at `runs/run-<id>/paypal-popup-before-login.png` and `check-<key>.png`, then adjust `SELECTORS` in `backend/app/agent/paypal_flow.py`. Live timeouts are in `LIVE_TIMEOUTS`.
7. Bad store, live PayPal: same command with `--cassette day3_checkout_flaws_on --flaws on`. Expect a purchase and a score of 49 (rules `2026-11-05.3`).
8. Live Groq (optional): `--llm groq --record live_off_1 --flaws off --checkout --paypal sandbox`, then `--flaws on --record live_on_1`. The recorded cassettes can be replayed later with `--llm mock --cassette live_off_1`.
9. Check the payment in the sandbox merchant account, then send me the CLI output (or add it to METRICS.md).

---

## 2026-11-05 (Day 1)

Done
- Repo scaffold: `store/`, `backend/`, `frontend/`, MIT LICENSE, `.gitignore`, `.env.example`, CLAUDE.md, Day 1 docs.
- PayPal research: JS Web SDK v6 (`/web-sdk/v6/core`) + Orders v2. Notes in `docs/research/paypal.md`.
- Demo store "Fernhill Ceramics": 4 products (1 sold out), product/checkout/thanks pages, PayPal v6 button. 4 flaws behind toggles (default ON) at `/store/admin` and `PUT /store/admin/flaws.json`.
- Backend: `GET /api/health`, `POST /api/paypal/orders`, `POST /api/paypal/orders/{id}/capture`, `GET /api/paypal/orders/{id}`. Orders + capture fees stored in SQLite.
- Frontend: Vite + React + TS placeholder that reads `/api/health`. Builds clean.
- Tests: 23 passing (API + store toggles). Live smoke test of all store pages and the explicit "PayPal not configured" errors.

In progress
- Manual sandbox purchase: code is ready, needs `PAYPAL_CLIENT_ID` / `PAYPAL_CLIENT_SECRET` in `.env` (user).

Next (Day 2)
- runs / steps / failures tables, Playwright tool layer, Groq tool-calling loop, deterministic flaw detectors.

Blockers
- No sandbox credentials in `.env` yet, so no real PayPal call has been made.
- Not a git repo yet; user to `git init` and commit (agent does not run git writes).
