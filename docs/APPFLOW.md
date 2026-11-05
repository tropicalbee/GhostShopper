# App flow

## Merchant (user) flow

1. Open the dashboard. The demo store URL is preset (scope lock: one store).
2. Click **Run mystery shopper**. Steps stream in: page visited, action taken, what the agent saw.
3. Run ends. Dashboard shows: score (0-100), sub-scores, failures grid (stage, severity, evidence), fix list ordered by points recoverable, checkout verification (order, capture, amount, fees), market check (Channel3 comparison).
4. Apply fixes (demo: toggle flaws off at `/store/admin`).
5. Rerun. Compare runs side by side: score up, failures down, purchase captured.

## Manual checkout flow (built, D1)

Product page -> (if `extra_checkout_step`) details form -> checkout page -> PayPal button -> PayPal popup (sandbox buyer login, approve) -> `onApprove` -> `POST /api/paypal/orders/{id}/capture` -> thanks page with order and capture ids.

## Shopper agent loop (D2-D3)

The agent is a real tool-calling loop. The LLM picks every action; nothing is scripted.

1. **Start run.** Insert `runs` row, snapshot flaws, open browser (Playwright locally, Kernel for real runs), load the store home page.
2. **Prompt.** System: "You are an AI shopping agent. Goal: buy one <product> for the user. Use only the tools. Report what blocked you." User: goal + store URL.
3. **LLM call** (Groq, tools enabled). The model returns one or more tool calls.
4. **Execute each tool** in the browser:
   - `read_page()`: visible text, links and buttons with ids, form fields, JSON-LD found. No images.
   - `navigate(url)`, `click(element_id)`, `fill(element_id, text)`, `select(element_id, option)`.
   - `pay_with_paypal()`: clicks the PayPal button and completes the sandbox popup with the test buyer (D3).
   - `finish(outcome, notes)`: ends the run.
5. **Record step**: tool, args, observation, URL, screenshot, timing -> `steps`.
6. **Run detectors** (deterministic, after each page load / action): price text present, Product JSON-LD present and valid, primary CTA identifiable (semantic button/link with clear label), steps between product and payment, popup/capture result. Each miss -> `failures` row with evidence.
7. **Append observation** to the conversation and go to 3.
8. **Stop** on `finish`, step limit (~25), timeout, or unrecoverable error. Set `runs.outcome`.
9. **Post-run**: verify order (D4: amounts match catalog, capture COMPLETED, fees present), Channel3 market check (D4), compute score (D5, pure function of failures + verification), ask the LLM to write a plain-language fix for each failure (explanations only).
