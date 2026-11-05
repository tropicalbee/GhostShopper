# GhostShopper

See your store through an AI shopper's eyes.

Built for the PayPal AI Hackathon 2026. Work in progress: the full README (problem, audience, hosted URL, tools used) lands on Day 6.

## Local setup

Requirements: Python 3.11+, Node 20+.

```bash
python -m venv .venv
.venv\Scripts\python -m pip install -r backend/requirements-dev.txt   # macOS/Linux: .venv/bin/python
cp .env.example .env    # fill in PAYPAL_CLIENT_ID and PAYPAL_CLIENT_SECRET (sandbox)

.venv\Scripts\python -m uvicorn backend.app.main:app --reload --port 8000
```

- Demo store: http://localhost:8000/store/
- Flaw toggles: http://localhost:8000/store/admin
- API health: http://localhost:8000/api/health

Tests: `.venv\Scripts\python -m pytest`

Mystery shopper agent (needs the browser once: `$env:PLAYWRIGHT_BROWSERS_PATH="0"; .venv\Scripts\python -m playwright install chromium`):

```bash
# replayed LLM, all flaws on, browse only
.venv\Scripts\python -m backend.app.agent --llm mock --cassette day2_flaws_on --flaws on
# full purchase against a server started with PAYPAL_MODE=mock (no PayPal calls)
.venv\Scripts\python -m backend.app.agent --llm mock --cassette day3_checkout_flaws_off --flaws off --checkout --paypal mock
# live Groq (GROQ_API_KEY + GROQ_MODEL in .env)
.venv\Scripts\python -m backend.app.agent --llm groq --flaws on
```

Frontend (dev):

```bash
cd frontend
npm install
npm run dev     # http://localhost:5173, proxies /api and /store to :8000
```

## License

MIT
