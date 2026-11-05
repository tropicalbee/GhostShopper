# One-command setup for a fresh clone (Windows PowerShell):  powershell -ExecutionPolicy Bypass -File scripts\setup.ps1
# Creates .venv, installs Python deps and Chromium (inside .venv), installs frontend deps, creates .env from
# .env.example if it does not exist (never overwrites), then runs the test suite.
$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)

if (-not (Test-Path .venv)) { python -m venv .venv }
.venv\Scripts\python -m pip install --upgrade pip
.venv\Scripts\python -m pip install -r backend/requirements-dev.txt

$env:PLAYWRIGHT_BROWSERS_PATH = "0"   # browsers inside .venv, nothing in your user profile
.venv\Scripts\python -m playwright install chromium

if (-not (Test-Path .env)) {
    Copy-Item .env.example .env
    Write-Host "Created .env from .env.example. Fill in your sandbox keys before running live."
}

Push-Location frontend
npm install
npm run build
Pop-Location

.venv\Scripts\python -m pytest -q
Write-Host ""
Write-Host "Done. Start the app:   .venv\Scripts\python -m uvicorn backend.app.main:app --port 8000"
Write-Host "Mock PayPal instead:   `$env:PAYPAL_MODE='mock'; .venv\Scripts\python -m uvicorn backend.app.main:app --port 8000"
Write-Host "Demo state:            .venv\Scripts\python -m backend.app.seed"
