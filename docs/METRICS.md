# Metrics

## 2026-11-05 (Day 1)

| What | Value |
|---|---|
| Backend + store tests | 23 passed, 0 failed (~3-4 s) |
| Frontend `vite build` | 0.3 s, clean `tsc -b` |
| Real PayPal sandbox orders | 0 (no credentials yet) |
| Agent runs | none yet (Day 2) |

## 2026-11-05 (Day 2): browse runs, mock LLM (replayed cassettes), local Playwright Chromium

Score rules `2026-11-05.1`. Payment checks (20 pts) are "not tested" in browse-only runs, so 80 is the browse maximum.

| Run | Flaws | LLM | Outcome | Steps | Score | Failed checks | Wall time |
|---|---|---|---|---|---|---|---|
| 1 (CLI) | all ON | mock `day2_flaws_on` | reached_checkout | 14 | **20** | price_in_text, structured_data, stock_readable, clear_buy_button, no_extra_steps | 13.5 s |
| 2 (CLI) | all OFF | mock `day2_flaws_off` | reached_checkout | 8 | **80** | none | 9.8 s |
| 3 (API) | all ON | mock `day2_flaws_on` | reached_checkout | 14 | **20** | same as run 1 (reproducible) | ~12 s |

Sub-scores, flaws ON: discover 10/10, details 0/50, checkout 10/20, payment 0/20.
Sub-scores, flaws OFF: discover 10/10, details 50/50, checkout 20/20, payment 0/20.
Live Groq: not run (GROQ_API_KEY / GROQ_MODEL not configured).

## 2026-11-05 (Day 3): checkout runs, mock LLM + PAYPAL_MODE=mock (no PayPal calls)

| Run | Flaws | Scenario | Outcome | Steps | Score | Failed checks | Order (gross / fee / net) | Wall time |
|---|---|---|---|---|---|---|---|---|
| 4 (CLI) | all ON | ok | purchased | 15 | **40** | price_in_text, structured_data, stock_readable, clear_buy_button, no_extra_steps | 24.00 / 1.33 / 22.67 | 22.3 s |
| 5 (CLI) | all OFF | ok | purchased | 9 | **100** | none | 24.00 / 1.33 / 22.67 | 19.9 s |
| 6 (API) | all OFF | capture_declined | blocked | 9 | **95** | capture_completed (INSTRUMENT_DECLINED) | not captured, not linked | ~15 s |

Failure scenarios (e2e tests, flaws OFF): no_button 80, popup_blocked 85, approval_stuck 90, capture_declined 95.
Live sandbox checkout: not run (by instruction). Live Groq: not run (not configured).

## Test suite

| Date | Tests | Result | Time |
|---|---|---|---|
| 2026-11-05 Day 1 | 23 | all pass | ~3 s |
| 2026-11-05 Day 3 | 65 (incl. 12 browser e2e) | all pass | 217 s |
