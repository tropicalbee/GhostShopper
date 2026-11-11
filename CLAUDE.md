# GhostShopper

PayPal AI Hackathon 2026. Deadline Nov 12, 12:00pm PT; aim to submit Nov 11.
Tagline: "See your store through an AI shopper's eyes."

Follow this brief every session.

## Problem

PayPal wants small merchants to be discoverable and buyable by AI shopping agents (Agent Ready, Store Sync). Merchants can't see how an AI agent experiences their store.

## What it does

1. Mystery shopper agent: a browser agent visits a merchant store like an AI shopping agent, tries to find a product, read details and check out, and logs every failure with evidence.
2. Market check: Channel3 compares the merchant's products with similar products.
3. Checkout test: real PayPal sandbox purchase (Orders v2 create + capture).
4. Verify: order, capture, amount and fees match.
5. Scorecard: agent-readiness score + prioritized fix list in an AG Grid dashboard.

Demo flow: bad store -> run -> low score + failures -> apply fixes -> rerun -> higher score + successful purchase.

## Layout

- `store/`: demo shop with PayPal checkout and deliberate flaws, each behind a toggle: price only in an image, missing structured product data, ambiguous buy buttons, an extra checkout step.
- `backend/`: FastAPI.
- `frontend/`: React + Vite + TS, AG Grid Community.
- `docs/`: tracking files (see below).

## Constraints

- Python 3.11+. SQLite only (no Postgres).
- Local Playwright for dev, Kernel only for real runs.
- NVIDIA Nemotron (OpenAI-compatible endpoint) for the LLM; Groq free tier is a supported alternative.
- PayPal sandbox only, current JS SDK version (v6 Web SDK, `https://www.sandbox.paypal.com/web-sdk/v6/core`).
- AG Grid Community features only.
- Render free tier for deploy.

## Rules

- The shopper agent is a real tool-calling loop, not a fixed script.
- The readiness score is deterministic, never computed by the LLM. The LLM only navigates and explains fixes.
- No secrets in git. Secrets live in `.env` (gitignored); `.env.example` lists the variables.
- Never silently fall back to sample data. Missing config is an explicit error.
- Small commits. The user runs all git write commands; the agent only recommends checkpoints and messages.

## Scope lock

One store, one product flow, one score. No accounts, no multi-store.

## Submission checklist

MIT LICENSE, README (problem, audience, setup, hosted URL, tools used), Render deploy, fresh-clone test, video under 3 min, Devpost description.

## Plan

- D1: repo + store + sandbox checkout.
- D2: shopper agent navigation + failure logging.
- D3: agent completes checkout.
- D4: Channel3 + verification.
- D5: scoring + dashboard.
- D6: deploy + README.
- D7: video + submit.

## DOCS

All docs live in `docs/`. Keep each one short (1-2 pages max); this is a 7-day build. Never let them grow into essays.

Written on Day 1 (update when the design changes):
- `PRD.md`: problem, audience (small merchants preparing for AI shopping agents), features, demo flow, out-of-scope.
- `TRD.md`: architecture, stack, APIs (PayPal Orders v2 + current JS SDK, Kernel, Channel3, Nemotron/Groq), constraints.
- `SCHEMA.md`: SQLite tables (runs, steps, failures, orders, scores) with fields.
- `APPFLOW.md`: user flow, plus the shopper agent's tool-calling loop step by step.
- `PLAN.md`: the 7-day plan, with a checkbox per task.
- `principles.md`: the RULES and SCOPE LOCK sections from this file.

Maintain every session:
- `PROGRESS.md`: dated entries: done, in progress, next, blockers.
- `issues-and-fixes.md`: dated entries: what broke, root cause, fix.
- `PLAN.md`: tick off finished tasks.
- `DECISIONS.md`: design choices, why, and what was rejected.
- `METRICS.md`: every number from test runs (scores, success rates, timings).
- `CHANGELOG.md`: changes per day, for the "built during the hackathon" section.

Later:
- `UI_SPEC.md`: write on Day 5, before building the dashboard.
- `optimization.md`: only if time allows after Day 6.
- `research/`: one file of links and key notes from the PayPal, Kernel and Channel3 docs we use.

## SESSION RITUAL

- Start of every session: read CLAUDE.md, `docs/PLAN.md` and the latest `docs/PROGRESS.md` entry, then tell the user what today's goal is.
- End of every session: update `PROGRESS.md`, `issues-and-fixes.md` and `PLAN.md`, then commit them. The user runs all git write commands (global rule); the agent prepares the exact `git add` / `git commit` commands and messages.

## SKILLS

Use installed skills only when the phase needs them:

- Frontend and UI/UX design skills: Day 5 dashboard only, after `UI_SPEC.md` is written.
- The demo store must stay plain and realistic, like a real small-merchant site. Never polish it with design skills; its flaws are the point.
- SEO audit skill: not during the build; only if time allows after Day 6.
- Markdown docs (README, docs/*.md, video script, Devpost text): write and revise them with the humanizer skill (`humanizer:humanizer`). They should read like the user wrote them: plain and direct, with no AI writing tells (no dashes in prose, no bold labels on every bullet, no "not X but Y").

## Dev commands

- Backend + store: `.venv\Scripts\python -m uvicorn backend.app.main:app --port 8000` from the repo root (avoid `--reload` when using `/api/runs` on Windows). Store at `http://localhost:8000/store/`, flaw toggles at `/store/admin`. `PAYPAL_MODE=mock` for the fake PayPal (no PayPal calls).
- Browsers: `$env:PLAYWRIGHT_BROWSERS_PATH="0"; .venv\Scripts\python -m playwright install chromium` (installs inside `.venv`).
- Agent: `.venv\Scripts\python -m backend.app.agent --llm mock --cassette day2_flaws_on --flaws on` (add `--checkout --paypal mock` against a mock server; `--llm live --record <name>` for live).
- Demo state: `.venv\Scripts\python -m backend.app.seed` (`--with-runs` against a mock server records a before/after pair).
- Hosted examples: `.venv\Scripts\python -m backend.app.examples export 31 34` bundles real runs into `backend/app/examples/`; `EXAMPLE_RUNS=1` loads them at startup.
- Compare runs: `.venv\Scripts\python -m backend.app.agent.compare --last`. Reword fixes: `python -m backend.app.agent.explain <run>`.
- Evaluation: `python -m backend.app.eval benchmark --matrix classic|random`, `... propose`, `... judge <run>`. Market check: `python -m backend.app.market <sku>`.
- Setup on a fresh clone: `scripts\setup.ps1` or `scripts/setup.sh`.
- Tests: `.venv\Scripts\python -m pytest` (browser e2e tests skip if Chromium is not installed).
- Frontend: `cd frontend && npm run dev` (proxies `/api` and `/store` to port 8000).
