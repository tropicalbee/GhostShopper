# App flow

## Merchant (user) flow

1. Open the dashboard (D5). The demo store URL is preset (scope lock: one store).
2. Click **Run mystery shopper**. Steps stream in: page visited, action taken, what the agent saw.
3. Run ends. Dashboard shows: score (0-100), sub-scores, failures grid (stage, severity, evidence), fix list ordered by points recoverable, checkout verification, market check (D4).
4. Apply fixes (demo: toggle flaws off at `/store/admin`).
5. Rerun. Compare: score up, failures down, purchase captured.

Today (D3) runs start from the CLI (`python -m backend.app.agent`) or `POST /api/runs`.

## Manual checkout flow (D1)

Product page -> (if `extra_checkout_step`) details form -> checkout -> PayPal button -> PayPal popup (sandbox buyer login, approve) -> `onApprove` -> `POST /api/paypal/orders/{id}/capture` -> thanks page with order and capture ids.

## Shopper agent loop (built D2-D3, `backend/app/agent/loop.py`)

The LLM picks every action; nothing is scripted. Checks are evaluated by code, never by the LLM.

1. **Prepare** (`service.py`): validate LLM config (Groq key+model, or a cassette), and for checkout runs the payment config. Missing config is an explicit error before any run row exists. Set flaws (`--flaws on|off|keep`), snapshot them.
2. **Start run**: insert `runs` row, launch local Playwright Chromium.
3. **Prompt**: system rules + goal ("find the mug, read price and stock, reach checkout", plus "pay with PayPal" for checkout runs).
4. **LLM call** with tools: `open_page`, `find_elements`, `read_text`, `click`, `fill_form`, `take_screenshot`, `finish`, and `pay_with_paypal` (checkout runs only). Clicking the PayPal button with `click` is refused.
5. **Execute** each tool call; screenshot the page; record a `steps` row.
6. **Detect** (`engine.py` + `checks.py`): collect DOM facts and record checks. Product page (title contains target): `product_found`, `price_in_text`, `structured_data`, `stock_readable`, `clear_buy_button`. Checkout page: `checkout_reached`, `no_extra_steps` (forms the agent had to fill between product and checkout). Failed checks get a full-page screenshot, selector and reason.
7. **Append** the observation, go to 4. Stop on `finish`, 25 steps, or an error.
8. **Finalize**: unreached checks are recorded as failed (`product_found`, `checkout_reached`) or not tested (later stages); compute and save the score.

## pay_with_paypal (D3, `agent/paypal_flow.py`)

1. Must be on checkout. Wait for a visible `<paypal-button>` -> `paypal_button_found`.
2. Click, wait for the popup -> `popup_opened` (fails if blocked).
3. Popup screenshot (before typing). Log in with the sandbox buyer (email -> Next -> password -> Log In; skipped if already logged in), click approve, wait for the popup to close -> `payment_approved` (fails on timeout, with the stuck stage).
4. Wait for the store's thanks page or its error message; confirm via `GET /api/paypal/orders/{id}` that order and capture are COMPLETED; link the order to the run -> `capture_completed`.

Modes: `PAYPAL_MODE=mock` on the server serves a mock SDK + popup (same element ids as PayPal's pages) and a fake Orders client; scenarios `ok`, `no_button`, `popup_blocked`, `approval_stuck`, `capture_declined` via `PUT /mock-paypal/scenario`. `PAYPAL_MODE=sandbox` (default) is the real thing and needs PayPal + buyer credentials, or the run is refused.
