#!/usr/bin/env bash
# One-command setup for a fresh clone (macOS/Linux):  bash scripts/setup.sh
# Creates .venv, installs Python deps and Chromium (inside .venv), installs frontend deps, creates .env from
# .env.example if it does not exist (never overwrites), then runs the test suite.
set -euo pipefail
cd "$(dirname "$0")/.."

[ -d .venv ] || python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r backend/requirements-dev.txt

export PLAYWRIGHT_BROWSERS_PATH=0   # browsers inside .venv
if [ "$(uname)" = "Linux" ]; then
  .venv/bin/python -m playwright install --with-deps chromium
else
  .venv/bin/python -m playwright install chromium
fi

if [ ! -f .env ]; then
  cp .env.example .env
  echo "Created .env from .env.example. Fill in your sandbox keys before running live."
fi

(cd frontend && npm install && npm run build)

.venv/bin/python -m pytest -q
echo
echo "Done. Start the app:   .venv/bin/python -m uvicorn backend.app.main:app --port 8000"
echo "Mock PayPal instead:   PAYPAL_MODE=mock .venv/bin/python -m uvicorn backend.app.main:app --port 8000"
echo "Demo state:            .venv/bin/python -m backend.app.seed"
