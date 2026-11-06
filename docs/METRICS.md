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
| 2026-11-06 providers, hardening, speed | 228 (173 without a browser, 55 in a real browser) | all passed | 57 s and 207 s |

## Frontend build (2026-11-06)

| Chunk | Size | Gzipped |
|---|---|---|
| Main (Home, Live, Results, Before and after) | 625 kB | 195 kB |
| Advanced view (AG Grid, charts), loaded on demand | 1,343 kB | 374 kB |

## Frontend build (2026-11-06, after the speed pass)

The table above is the earlier build, for comparison.

| Chunk | Size | Gzipped |
|---|---|---|
| Main JS | 347.31 kB | 110.54 kB |
| Advanced view (AG Grid, charts), loaded on demand | 1,622.64 kB | 456.49 kB |
| CSS | 62.43 kB | not measured |

## Lighthouse (2026-11-06)

Scores are performance / accessibility / best practices / SEO.

| Page | Desktop | Mobile |
|---|---|---|
| `/` | 100 / 100 / 100 / 100 | 93 / 100 / 100 / 100 |
| `/#/checks` | 100 / 100 / 100 / 100 | 95 / 100 / 100 / 100 |

Before the meta description was added, SEO was 90 on every page. Performance was 92 on `/` mobile, 97 on `/#/checks` desktop and 79 on `/#/checks` mobile. The 79 was partly noise from parallel CPU load.

## Store redesign (2026-11-06)

| What | Value |
|---|---|
| Full test suite after the redesign and after each later round | 228 passed (about 4 minutes) |
| Day 2 fixed-store cassette run, with the related-products bug | 77 / 100 |
| Day 2 fixed-store cassette run, after the fix | 80 / 100 (payment is not part of a Day 2 run) |
| Store tests plus agent and checkout e2e, after the last CSS tweaks | 42 passed |
| Hallmark sloplint on rendered pages and `store/static/style.css` | 0 FAIL |
| Impeccable detect | 0 findings |

## Real sandbox runs (2026-11-07)

All runs used `--llm scripted --flaws off --checkout --paypal sandbox`. Runs 14 and 15 were headless, 16 to 18 headed.

| Run | Result | Score |
|---|---|---|
| 14 | `paypal_button_missing` after the 20 s button timeout (store failure) | 75 / 100 |
| 15 | `approval_timeout` after 120 s (environment) | 100 / 100 on 82 of 100 points |
| 16 | `approval_timeout` after 120 s (environment) | 100 / 100 on 82 of 100 points |
| 17 | `approval_timeout` after 120 s (environment) | 100 / 100 on 82 of 100 points |
| 18 | purchased, nothing excluded | 100 / 100 |

Run 18 payment

| What | Value |
|---|---|
| Order status / capture status | COMPLETED / COMPLETED |
| Gross | USD 24.00 |
| PayPal fee | 1.33 |
| Net | 22.67 |
| Order created / captured | 19:49:52 UTC / 19:50:05 UTC (13 s) |
| Agent steps | 9 |
| Order, capture, amount, fees | all verified |

Other numbers

| What | Value |
|---|---|
| Credential smoke test | OAuth token 200, a 1.00 USD order created 201 CREATED |
| Full test suite after the `paypal_error_page` change | 234 passed (277.6 s) |
| Full test suite after the five PayPal features | 287 passed, 0 skipped (browser e2e ran) |
| Frontend build after the five PayPal features | clean |

## Live test of the PayPal features (2026-11-07)

Runs started through `POST /api/runs` with one cookie, `--llm scripted`, real sandbox. Times are UTC as stored.

| Run | Setup | Result | Score |
|---|---|---|---|
| 19 | headless, flaws off, checkout | `approval_timeout` after 120 s, stuck at the password step (environment), order 9M109243TS5211110 left CREATED | 100 / 100 on 82 of 100 points |
| 20 | headed, flaws off, checkout | purchased, hand-assisted (see below) | 100 / 100 |
| 21 | headed, budget 20.00 | `over_budget`, no order, outcome blocked, 15 s | 100 / 100 on 75 of 100 points |
| 22 | flaws on, no checkout, no PayPal call | gave up, 25 steps, 14 s | 18 / 100 |

Run 20 payment

| What | Value |
|---|---|
| Order / capture | 3A787775X68465154 / 5V4554169H1404341, both COMPLETED |
| Gross / fee / net | USD 24.00 / 1.33 / 22.67 (effective fee 5.54%) |
| Order created / captured | 21:08:26 / 21:13:06 (4 min 40 s: the agent stalled on the review page and the user clicked Complete Purchase) |
| Refund | 5R334917CM111954P, COMPLETED, USD 24.00, `verified: true`, no mismatches |
| Refund time | 5.8 s for the API call, done 21:13:38 |
| Cache check | `GET /api/runs/20` right after the refund shows the refund fields |

PayPal readiness and product feed

| Run | PayPal readiness | Product feed |
|---|---|---|
| 20 (good store) | 28 / 100: button partial 8/20 (the scan ran before the button drew), SDK v6 20/20, the rest missing | 7 of 7 required columns, 11 columns, gtin, mpn and condition missing |
| 21 | 28 / 100, same pattern | same |
| 22 (flaws on) | 0 / 100, no PayPal found on 6 pages | 3 of 7 required (id, description, price and availability missing) |

Feed CSV for run 20 (`/api/runs/20/feed.csv`): 200, `text/csv`, header `id,title,description,link,image_link,price,availability,brand,gtin,mpn,condition`, one row, price `24.00 USD`. Run 22 has the same header and a row with only title, link and image_link filled.

Docs links used by the readiness panel: all six return 200. The v6, Pay Later, Venmo, checkout and card URLs each redirect to a current page. None is a 404.

UI at 1440 px and 375 px: no console errors or warnings on runs 20, 21 and 22. At 375 px the Simple view was 448 px wide before the fix and 375 px after. Advanced is tablet width and up by design, so it has no 375 px tabs.

PayPal budget used: 3 agent runs (19, 20, 21) and 1 refund.

After the live-test fixes: pytest 287 passed, 0 skipped (312.9 s); frontend build clean.
