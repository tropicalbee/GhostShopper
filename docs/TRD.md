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
- `backend/`: API, PayPal client, agent (`backend/app/agent/`: `loop` tool-calling loop, `browser` Playwright tools, `checks` + `engine` deterministic detectors, `paypal_flow` checkout, `llm` Groq/replay, `recorder` SQLite), `scoring` (pure).
- `PAYPAL_MODE=mock` swaps in `paypal_mock.py`: fake Orders client + mock v6 SDK/popup at `/mock-paypal/*`. Reported by `/api/health`. Default is `sandbox`.
- `frontend/`: React + Vite + TS, AG Grid Community. Dev server proxies `/api` and `/store` to :8000.

## Stack

Python 3.11+ (dev on 3.13), FastAPI, httpx, Jinja2, SQLite (stdlib `sqlite3`), pytest (+ anyio plugin for async tests). Node + Vite + React 19 + TypeScript. Playwright for Python; browsers installed inside the venv (`PLAYWRIGHT_BROWSERS_PATH=0`).

## External APIs

| API | Use | Notes |
|---|---|---|
| PayPal JS Web SDK v6 | Store's PayPal button | `https://www.sandbox.paypal.com/web-sdk/v6/core`; `paypal.createInstance({clientId, components:["paypal-payments"]})`, `findEligibleMethods`, `createPayPalOneTimePaymentSession({onApprove,onCancel,onError})`, `session.start({presentationMode:"auto"}, createOrderPromise)`. |
| PayPal Orders v2 | Server create + capture | `POST /v1/oauth2/token` (client credentials), `POST /v2/checkout/orders` (intent CAPTURE, items + breakdown), `POST /v2/checkout/orders/{id}/capture`. Fees from `captures[0].seller_receivable_breakdown`. Sandbox host hardcoded: `api-m.sandbox.paypal.com`. |
| Groq | LLM for navigation and fix explanations | Free tier, OpenAI-compatible `POST /openai/v1/chat/completions` with `tools`, via httpx (retries 429). Model set by `GROQ_MODEL`. Without it, runs replay recorded cassettes (`--llm mock`). |
| Kernel | Hosted browser for real runs | Local Playwright in dev. Same tool layer, different browser factory. |
| Channel3 | Market check: similar products | D4. |

## Key technical rules

- The order amount is computed server-side from `store/products.json`; the browser only sends SKU + quantity.
- Capture only orders this server created (checked in SQLite).
- Missing credentials return explicit errors (503 `PAYPAL_NOT_CONFIGURED`, "PayPal is not configured" on the checkout page). No sample-data fallback.
- Failures are detected by deterministic checks in the tool layer, not by the LLM. The score is a pure function of the recorded failures and checkout result.

## Constraints

SQLite only. Groq free tier (rate limits: keep runs under ~25 steps). PayPal sandbox only. AG Grid Community only. Render free tier (cold starts, ephemeral disk: the DB resets on redeploy, acceptable for a demo). Secrets only in `.env`.

## Scoring rubric

Rules version `2026-11-05.3`. The code in `backend/app/scoring.py` is the source of truth; this table should match it.

Every run records one outcome per check: pass, fail, excluded, or not tested. A failure's code (in `backend/app/failures.py`) says whether the store caused it. If it didn't (the buyer's bank declined, the browser blocked a popup, the run itself crashed), the check is excluded, and so is every check it stopped from running.

The score is `round_half_up(100 * earned / possible)`, where `possible` is 100 minus the points of excluded checks. Failed and untested checks earn nothing. If everything is excluded there's no score. A browse-only run (no payment) can reach 80 at most.

| Stage | Check | Points | Fails when |
|---|---|---|---|
| discover (5) | product_found | 5 | the agent never reached a page titled with the product |
| details (40) | price_in_text | 12 | there's no price text in `<main>`, e.g. it's only in an image |
| | currency_stated | 3 | a readable price has no currency, in the text or in JSON-LD |
| | structured_data | 12 | no Product JSON-LD, or it lacks name, price, priceCurrency or availability |
| | stock_readable | 4 | no stock status in the text or JSON-LD |
| | stock_consistent | 3 | the page says sold out but still offers a buy control |
| | image_alt_text | 3 | a product photo's alt is empty, a file name, or generic |
| | sale_claim_consistent | 3 | the "was" price or percent-off claim doesn't match the real price |
| checkout (30) | clear_buy_button | 10 | no real button or link labelled Buy, Add to cart or Checkout |
| | buy_button_unobstructed | 4 | something covers the buy control |
| | no_extra_steps | 6 | the agent had to fill a form between the product page and checkout |
| | checkout_reached | 6 | the agent never got to a checkout page with a payment button |
| | price_consistent | 4 | the checkout price differs from the product page price |
| payment (20) | paypal_button_found | 4 | no visible PayPal button |
| | popup_opened | 3 | no PayPal window; the store's fault if the click does nothing, the browser's if it blocked the popup |
| | payment_approved | 3 | login or approval didn't finish, a human check timed out, or someone cancelled (all excluded) |
| | capture_completed | 5 | capture error or no confirmation page (store); declined by the buyer's funding source (excluded) |
| | payment_verified | 5 | order vs advertised price, capture vs order, currency or capture id mismatch (store); pending capture or bad fee data from PayPal (excluded) |
| outcome (5) | task_completed | 5 | the agent gave up, looped, ran out of steps or kept timing out (store); stopped by something outside the store (excluded) |

If the agent never reaches the product page or checkout, product_found and checkout_reached fail. Later checks are marked not tested, or excluded when an environment failure is what stopped the run.

Fixes are listed failed first, then untested. task_completed goes after the failures that caused it, then by points, then by severity.
