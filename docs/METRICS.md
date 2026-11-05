# Metrics

Every number from our test runs. Scores depend on the rules version, so each table says which one it used.

## 2026-11-05 (Day 1)

| What | Value |
|---|---|
| Backend and store tests | 23 passed, 0 failed (about 3-4 s) |
| Frontend `vite build` | 0.3 s, clean `tsc -b` |
| Real PayPal sandbox orders | 0 (no credentials yet) |

## 2026-11-05 (Day 2): browse runs, mock LLM, local Chromium

Rules `2026-11-05.1`. Payment checks (20 points) aren't tested in browse runs, so 80 was the browse maximum.

| Run | Flaws | LLM | Outcome | Steps | Score | Failed checks | Wall time |
|---|---|---|---|---|---|---|---|
| 1 (CLI) | all on | mock `day2_flaws_on` | reached_checkout | 14 | 20 | price_in_text, structured_data, stock_readable, clear_buy_button, no_extra_steps | 13.5 s |
| 2 (CLI) | all off | mock `day2_flaws_off` | reached_checkout | 8 | 80 | none | 9.8 s |
| 3 (API) | all on | mock `day2_flaws_on` | reached_checkout | 14 | 20 | same as run 1 | about 12 s |

## 2026-11-05 (Day 3): checkout runs, mock LLM, PAYPAL_MODE=mock

Rules `2026-11-05.1`. No PayPal servers were contacted.

| Run | Flaws | Scenario | Outcome | Steps | Score | Failed checks | Gross / fee / net | Wall time |
|---|---|---|---|---|---|---|---|---|
| 4 (CLI) | all on | ok | purchased | 15 | 40 | the 5 classic flaw checks | 24.00 / 1.33 / 22.67 | 22.3 s |
| 5 (CLI) | all off | ok | purchased | 9 | 100 | none | 24.00 / 1.33 / 22.67 | 19.9 s |
| 6 (API) | all off | capture_declined | blocked | 9 | 95 | capture_completed | not captured | about 15 s |

## 2026-11-05 (tasks 1-11): scoring by cause, new checks, benchmark

Rules `2026-11-05.3` (18 checks, see TRD). Runs 1-6 above would score differently under these rules: the classic bad store went from 20 to 29 in browse runs, because it passes the new checks that its flaws don't touch.

### Demo pair from `python -m backend.app.seed --with-runs` (mock LLM, mock PayPal)

| Run | Flaws | Outcome | Score | Notes |
|---|---|---|---|---|
| 7 | classic 4 on | purchased | 49 | 5 store failures worth 44 points |
| 8 | all off | purchased | 100 | `compare 7 8`: +51, 5 fixed, 0 remaining, 0 new; order captured, 24.00 USD |

The seed command took 46.9 s, both runs included.

### Checkout failures by cause (end-to-end tests, flaws off)

| Scenario | Failed check | Cause | Score | Judged on |
|---|---|---|---|---|
| no_button | paypal_button_found | store | 75 | 100 |
| popup_blocked | popup_opened | environment | 100 | 79 |
| approval_stuck | payment_approved | environment | 100 | 82 |
| captcha, nobody approves | payment_approved (human_approval_timeout) | environment | 100 | 82 |
| capture_declined | capture_completed | environment | 100 | 85 |
| capture_amount_mismatch | payment_verified | store | 95 | 100 |
| fee_mismatch | payment_verified (fee_inconsistent) | environment | 100 | 95 |
| verification_required, a person approves | none | | 100 | 100 |

### Detection benchmark

Each worker runs its own store server with mock PayPal, and every run is a checkout run. Navigation used `scripted-navigator-v1`, which is rule-based and not an LLM, so these numbers measure the deterministic detectors. They say nothing about how well an LLM agent navigates.

| Benchmark | Runs | Precision | Recall | TP / FP / FN | Masked checks | Scores (min / mean / max) | Time |
|---|---|---|---|---|---|---|---|
| Each flaw alone, plus none | 11 | 1.0 | 1.0 | 13 / 0 / 0 | 0 | 84 / 92.3 / 100 | 95.8 s, 30.4 s per run |
| Classic matrix (all 16 combos of the 4 original flaws) | 16 | 1.0 | 1.0 | 40 / 0 / 0 | 0 | 49 / 75.2 / 100 | 132.0 s, 29.8 s per run |
| Random, 30 combos of 1-4 flaws from all 10 (seed 7) | 30 | 1.0 | 1.0 | 105 / 0 / 0 | 6, in 6 runs | 54 / 75.3 / 97 | 291.0 s, 36.8 s per run |

Every flaw was detected every time it appeared (random set: no_structured_data 14 runs, ambiguous_buttons, misleading_sale, oos_buyable and price_as_image 9 each, cookie_banner, currency_missing and extra_checkout_step 8 each, image_alt_missing and price_mismatch 6 each). There were no false positives and no failures in non-detector checks. All 57 runs ended in a mock purchase.

How to read this: we wrote both the flaws and the detectors, on one store, so a perfect score is a consistency check. A missed flaw here would mean a bug. It doesn't show that the detectors work on other stores or other kinds of flaws. The reports are in `data/eval/*/report.json` (not committed).

### LLM-as-judge (fix explanations)

Not valid until run live. These came from replayed cassettes, so they test the harness only.

| Run | Judge | Rated | Matches evidence (mean, 1-5) | Actionable (mean, 1-5) | Invented | Unsourced numbers |
|---|---|---|---|---|---|---|
| 7 | cassette `judge_classic` (`valid = 0`) | 5 | 4.8 | 4.4 | 0% | 0 |

### Market check (recorded fixtures, not live Channel3 data)

| Product | Comparables | Median | Our price | Versus median | Competitive |
|---|---|---|---|---|---|
| Speckled Stoneware Mug | 6 | 27.00 | 24.00 | -11.1% | yes |
| Pour-Over Coffee Dripper | 5 | 32.00 | 38.00 | +18.8% | no |
| Ash Glaze Serving Bowl | 5 | 64.00 | 52.00 | -18.8% | yes |
| Espresso Cup Set (4) | 2 (not findable) | 45.00 | 44.00 | -2.2% | yes, weak signal |

## Test suite

| Date | Tests | Result | Time |
|---|---|---|---|
| 2026-11-05 Day 1 | 23 | all passed | about 3 s |
| 2026-11-05 Day 3 | 65 (12 in a real browser) | all passed | 217 s |
| 2026-11-05 after tasks 1-7 | 111 | all passed | 381 s |
| 2026-11-05 after tasks 8-11 | 142 (about 30 in a real browser) | all passed | 338 s |
| 2026-11-06 dashboard | 168 | all passed | 187 s |
| 2026-11-06 checks per browser | 189 (21 access tests) | all passed | 177 s |
| 2026-11-06 Ledger redesign | 190 | all passed | 178 s |

## Frontend build (2026-11-06)

| Chunk | Size | Gzipped |
|---|---|---|
| Main (Home, Live, Results, Before and after) | 625 kB | 195 kB |
| Advanced view (AG Grid, charts), loaded on demand | 1,343 kB | 374 kB |
