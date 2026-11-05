# TRD: GhostShopper

## Architecture

One FastAPI process (one Render free web service):

```
browser ──> FastAPI (backend/app/main.py)
              ├── /api/health
              ├── /api/paypal/orders, /orders/{id}/capture   Orders v2 (sandbox)
              ├── /api/runs ...            (D2+) agent runs, steps, failures, scores
              ├── /store/...               demo store (store/app.py, mounted sub-app)
              └── /                        dashboard build (D5/D6: frontend/dist)
SQLite file (DATABASE_PATH)
Shopper agent: Groq LLM  <->  tools  <->  Playwright (local) | Kernel browser (real runs)
```

- `store/`: Fernhill Ceramics, a plain server-rendered shop (Jinja2). Flaw toggles in SQLite table `store_flaws`, edited at `/store/admin` or `PUT /store/admin/flaws.json`.
- `backend/`: API, PayPal client, (D2+) agent loop, detectors, scoring.
- `frontend/`: React + Vite + TS, AG Grid Community. Dev server proxies `/api` and `/store` to :8000.

## Stack

Python 3.11+ (dev on 3.13), FastAPI, httpx, Jinja2, SQLite (stdlib `sqlite3`), pytest. Node + Vite + React 19 + TypeScript. Playwright (D2).

## External APIs

| API | Use | Notes |
|---|---|---|
| PayPal JS Web SDK **v6** | Store's PayPal button | `https://www.sandbox.paypal.com/web-sdk/v6/core`; `paypal.createInstance({clientId, components:["paypal-payments"]})`, `findEligibleMethods`, `createPayPalOneTimePaymentSession({onApprove,onCancel,onError})`, `session.start({presentationMode:"auto"}, createOrderPromise)`. |
| PayPal Orders v2 | Server create + capture | `POST /v1/oauth2/token` (client credentials), `POST /v2/checkout/orders` (intent CAPTURE, items + breakdown), `POST /v2/checkout/orders/{id}/capture`. Fees from `captures[0].seller_receivable_breakdown`. Sandbox host hardcoded: `api-m.sandbox.paypal.com`. |
| Groq | LLM for navigation and fix explanations | Free tier, tool calling. Model set by `GROQ_MODEL`. |
| Kernel | Hosted browser for real runs | Local Playwright in dev. Same tool layer, different browser factory. |
| Channel3 | Market check: similar products | D4. |

## Key technical rules

- The order amount is computed server-side from `store/products.json`; the browser only sends SKU + quantity.
- Capture only orders this server created (checked in SQLite).
- Missing credentials return explicit errors (503 `PAYPAL_NOT_CONFIGURED`, "PayPal is not configured" on the checkout page). No sample-data fallback.
- Failures are detected by deterministic checks in the tool layer, not by the LLM. The score is a pure function of the recorded failures and checkout result.

## Constraints

SQLite only. Groq free tier (rate limits: keep runs under ~25 steps). PayPal sandbox only. AG Grid Community only. Render free tier (cold starts, ephemeral disk: the DB resets on redeploy, acceptable for a demo). Secrets only in `.env`.
