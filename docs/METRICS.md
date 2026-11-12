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

### Market check, live Channel3 (hosted site, 2026-11-12)

`GET /api/market/FH-MUG-01` on ghostshopper.onrender.com returned source `channel3` ("Live Channel3 search results."): 18 similar products (2 removed as duplicates or multi-packs), min $6.99, median $20.13, max $88.00. Our price $24.00 is 19.3% above the median, not competitive. Read-only GET.

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

## 2026-11-08 (blockers and audit fixes)

No live PayPal or Kernel runs this session, so no new run numbers.

| Check | Result |
|---|---|
| Backend tests | 313 passed, 1 warning |
| Frontend `npm run build` | succeeded |
| PayPal readiness, fixed store | 100 |
| PayPal readiness, flawed store (four PayPal toggles on) | 52 (about 46 in a real run with the extra checkout step) |

## 2026-11-09 (money hero, vault payment)

No live PayPal, Kernel or Nemotron runs, so no new run numbers.

| After | Backend tests |
|---|---|
| Password guard and docs | 319 passed |
| Money hero and `no_guest_checkout` | 334 passed (full suite); browser e2e files alone 32 passed |
| Vault payment, before the review fixes | 334 passed (full suite) |
| Vault review fixes | `test_vault.py` 17 passed |

## 2026-11-10 (ledger and flow checks)

Mock LLM, mock PayPal, scratch database, local Chromium.

| What | Value |
|---|---|
| `npm run build` | passes (main chunk 1,586 kB, size warning only) |
| `test_ledger.py` + `test_compare.py` | 26 passed |
| `seed --with-runs` pair | 24 to 100 (+76), 7 failures fixed, $24.00 captured, net $22.67 |
| Ledger row after a fresh server process | `matched` (was `pending` before the fix) |
| Full suite (user run) | 361 passed, 1 warning, 412 s |


## 2026-11-10 (purchase trace benchmark)

Command: `python -m backend.app.eval benchmark --matrix trace`. Mock PayPal, scripted navigator (not an LLM), scratch databases, local Chromium. This measures the purchase trace, which sits outside the score. The expected results are written by hand in `backend/app/eval/trace_truth.py`, one line of reasoning each. No expectation was changed to make a scenario pass.

32 scenarios from 26 mock purchases: 4 on a healthy store, 1 healthy store with PayPal capturing 1.00 too much, 5 purchase flaws where they bite, 4 price_mismatch outcomes, 11 flaws switched on where the PayPal outcome never triggers them, and 7 link cases (one healthy purchase, ids tampered with, then put back). Total time 144.6 s with 4 workers.

| Measure | Result |
|---|---|
| Scenarios passed | 31/32 |
| First mismatch correct | 31/32 |
| False mismatches on healthy runs | 0/4 |
| False mismatches where a flaw is on but not triggered | 0/11 |
| Broken link detection | 4/4 |
| Unknown not guessed | 2/3 |

The failing scenario: the store order has no PayPal order id. The trace can't reach any PayPal record, calls the capture "never charged" and reports `success_without_payment` for a store that says Paid. The expected answer is unknown with no mismatch. A real store that marks an order paid with no PayPal order at all is also worth a flag, so this one is a judgment call. It is listed as a known failure in `backend/tests/test_trace_matrix.py`.

Skipped on purpose: `fee_mismatch` (fees are not a trace field), the PayPal scenarios that never reach a capture, and price_mismatch with a wrong capture amount (two causes at once).

2026-11-11 rerun after the design change: 33 scenarios from 26 mock purchases, 214.5 s with 4 workers. Scenarios passed 33/33, first mismatch correct 33/33, false mismatches on healthy runs 0/4, where a flaw is on but not triggered 0/11, broken link detection 5/5, unknown not guessed 3/3. One expectation was changed by design decision: `link-store-order-id-missing` now expects `paid_without_paypal_reference` at the store order (a Paid order with no PayPal id is a fact about the store's records), with the PayPal stages unknown. A control was added: the same missing id on an awaiting_payment order must give no mismatch.

These are mock runs on our own demo store, so they check the trace logic against our labels. The only real sandbox evidence so far is run 34, one live purchase where all four ID links were ok.

## 2026-11-11 (live runs and suite)

Recorded by the CLI. Runs 31 to 37 used real services except where PayPal says none.

| Run | LLM | Browser | Store | PayPal | Score | Steps | Outcome |
|---|---|---|---|---|---|---|---|
| 30 | mock replay | local, headed | bad | mock | 49/100 | 16 | purchased |
| 31 | Nemotron | local, headed | bad (classic flaws) | sandbox | 49/100 | 20 | purchased, order 4PX60387GH784405X, capture 3UK25263HR129600H, 24.00 USD, fee 1.33, net 22.67 |
| 32 | Nemotron | local, headed | fixed | sandbox | 100/100 | 10 | purchased, order 0FN59308RY982621L, capture 62L48939HA821962H |
| 33 | Nemotron | local | sauce-demo.myshopify.com | none | 62/100 (84 of 100 points judged) | 11 | browse only, 5 issues worth 28 points |
| 34 | Nemotron | local | fixed | sandbox | 100/100 | 11 | purchased, store order 1047, order 9P171796J2912013M, capture 7GJ425816G1525704 |
| 36 | Nemotron | Kernel | Shopify | none | none | | hung about 8 min on service worker requests, killed by hand |
| 37 | Nemotron | Kernel | Shopify | none | 62/100 | 19 | browse only, same 5 issues as run 33, session deleted |

Run 33 issues: no Product JSON-LD, no stock status, alt text "Product Image", no PayPal button, task not completed. The redirect guard did not trigger. Cassettes: `live_sandbox_flaws_on`, `live_sandbox_flaws_off`, `live_shopify_sauce`. In run 34 all four ID links were ok on real sandbox data, and PayPal echoed `custom_id=1047` on the order and the capture. Kernel credit after the session: 4.95 of 5.00 USD.

| Full suite | Tests | Result | Time |
|---|---|---|---|
| After the reason and nvidia fix | 451 | passed | 778 s |
| After the ID links | 469 | passed | about 11 min |
| After the trace matrix | 470 | passed | 620 s |
| After paid without PayPal reference | 472 | passed | 788 s |
| After the Kernel fix and env guard | 488 | passed | 616 s |

## 2026-11-11 (session 5, mock only)

| What | Value |
|---|---|
| `test_market.py` after the duplicate and multi-pack filter | 24 passed |
| Full suite (click-through agent run) | 523 passed |
| `npm run build` | ok |
| Click-through smoke test, mock PayPal | store and dashboard pages at 1440 and 390 px, 0 bugs, no horizontal overflow |

## 2026-11-12 (session 7, video take, real Sandbox)

| What | Value |
|---|---|
| Run 47, bad store, Nemotron 3.5 Lightning | 18/100, gave up after 25 steps, 201 s |
| Run 48, fixed store, vault payment | 100/100, purchased in 11 steps, $24.00 captured, $1.33 fee, $22.67 net, 4 of 4 IDs linked |
| Nemotron 3.5 Super VL 120B reply time | about 40 s per step, one-word probe 43.6 s after two 503s |
| Nemotron 3.5 Lightning reply time | 2.3 to 2.7 s with a tool call |
| Recorded take | 364.6 s of footage |
| Tests after the popup fix and payment option | 76 passed (PayPal/checkout), 79 passed (runs/vault/API) |

## 2026-11-12 (session 8, video v2 takes, real Sandbox, vault payment, Nemotron 3.5 Lightning)

| What | Value |
|---|---|
| Run 50, price as image + no product data + never marks paid | purchased in 10 steps, 65/100, capture COMPLETED $24.00, fee $1.33, net $22.67, store order #1071 `awaiting_payment`, first mismatch at the store order (status: expected Paid, got Awaiting payment), 4 of 4 ID links ok |
| Run 51, every flaw off | purchased in 11 steps, 100/100, store order #1072 `paid`, $24.00 captured, $22.67 net, no mismatches |
| Run 50 to 51 | 65 to 100 (+35): price as text 12, structured data 12, stock readable 4 |
| Run 52, hidden instructions for AI agents | purchased at $24.00 in 11 steps, one finding at step 2 (off-screen review text, hidden from people), the shopper did not follow it |
| Video v2 | 2:54.5, Kokoro "Heart" voice time-stretched 4%, original ambient pad |

## 2026-11-12 (session 9, WebMCP, catalog readiness, live, PayPal Sandbox)

Model for runs 53 to 57: NVIDIA Nemotron 3.5 Super VL 120B (`nvidia/nemotron-3.5-super-vl-120b-a12b`). Local Chromium, headed unless said. Live numbers only in this table; mock numbers stay in the sections above.

| What | Value |
|---|---|
| Native discovery, PayPal showcase | 4 tools (`shopping.searchProducts`, `shopping.getProduct`, `shopping.initiateCheckout`, `shopping.completeCheckout`), source native WebMCP. Page loads PayPal web-sdk v6 core and PayPal's WebMCP script |
| Native discovery, `sauce-demo.myshopify.com` (not built by us, no PayPal SDK) | 12 tools: ask_business, browse_store, cancel_cart, create_cart, get_cart, get_product, get_ucp_profile, manage_orders, proceed_to_checkout, search_catalog, show_variant, update_cart. Discovery only. Its robots.txt and tool descriptions hold text aimed at agents, treated as data |
| Run 53, WebMCP on Fernhill, headless | PayPal order created (store cart #1074). Buyer approval stuck at PayPal's password step in a headless browser. Outcome blocked, nothing captured |
| Run 54, WebMCP on Fernhill, flaws price_as_image + no_structured_data + never_marks_paid | 4 tool calls (search, getProduct, initiateCheckout, completeCheckout) plus the runtime's approval and read-back. Capture COMPLETED $24.00 (capture 7YC63355SU675642L). Store order #1075 Awaiting payment. First mismatch at the store order. 4 of 4 ID links ok. 24.00 in search, product, checkout and capture. Tool checks 7 pass, order_recorded fail. 39 s |
| Run 57, browser agent, same store and flaws, same model, vault payment | 10 agent steps, 35 s, readiness 65/100 (price as text 12, structured data 12, stock 4 lost). Capture COMPLETED $24.00, fee 1.33, net 22.67. Store order Awaiting payment, same first mismatch, 4 of 4 links |
| Compare 57 vs 54 (code verdict) | "WebMCP bought in 4 tool calls; the browser agent took 10 steps. Both paths hit the same first mismatch: the store order still says Awaiting payment." Wall time similar (35 s browser, 39 s WebMCP): the WebMCP path includes the buyer's PayPal approval page that the vault payment skips. No speed claim |
| Run 56, WebMCP on PayPal's showcase (external demo) | Bought a Starbucks gift card at $25.00, buyer approved in the PayPal Sandbox, `completeCheckout` COMPLETED. 25.00 in search, product and checkout. Tool checks 7 pass, order_recorded not tested (no store order on PayPal's merchant). 76 s |
| Run 55 | Earlier showcase purchase; its price parsing was then fixed (see issues-and-fixes) |
| Catalog readiness, demo store | 12/12 machine-readable with flaws off, 0/12 with `no_structured_data` (also 0/12 with `currency_missing`) |
| Catalog readiness, `sauce-demo.myshopify.com` | 3 product pages found, 2 checked, 0 of 2 machine-readable (no Product JSON-LD, matching runs 33 and 37). Third page refused with HTTP 429 after polite retries. One page at a time, 2 s apart, Retry-After honoured, 60 s budget, no percent when too few pages could be read |
| Full test suite | 643 passed, 1 failed (a health-keys test pinned to the old `/api/health` fields; updated for the new field) |
| That test file plus all WebMCP test files | 85 passed |
| New test files | `test_webmcp_*` (rpc, discover, e2e, compare, checks, api), `test_catalog_readiness` (25 tests) |

### Shopper vision (same session, live, PayPal Sandbox, vault payment, headed)

Shopper model and `VISION_MODEL` were both `nvidia/nemotron-3.5-super-vl-120b-a12b`.

| What | Value |
|---|---|
| Run 59, price_as_image + no_structured_data | Step 6: `look_at_page` ("What is the price and stock status of the Speckled Stoneware Mug?"), answer "The price is $24.00 and it is in stock (ships from Asheville in 3 business days)." Bought in 12 steps, capture COMPLETED $24.00 (fee 1.33, net 22.67), store order #1078 Paid. Readiness 65/100 (price_in_text, structured_data, stock_readable still fail) |
| Run 58, price_as_image only | Vision available, `look_at_page` never called. Read 24.00 USD from the structured data, bought, 84/100, order #1077 Paid |
| Vision tests | `test_vision.py` 26 tests (fake vision model, no network); with provider, safety and recorder tests 79 passed; e2e and guards 16 passed |

## Hosted real run 5 (2026-11-12)

The first real run on the hosted site, in Kernel, against the flawed demo store. Read from the hosted run record. Model: `nvidia/nemotron-3.5-super-vl-120b-a12b`.

| What | Value |
|---|---|
| Browser, PayPal, payment | Kernel, sandbox, popup (no saved vault buyer on the hosted database) |
| Started, finished | 17:34:00 UTC, 17:43:07 UTC (9 min 7 s) |
| Outcome, end reason | blocked, step_limit |
| Steps | 25 |
| Score | 41/75 (6 checks excluded as not the store's fault; discover 5, details 9, checkout 10, payment 7, outcome 0) |
| Store failures | price_in_text, structured_data, clear_buy_button, no_extra_steps, stock_readable |
| Step 18, `pay_with_paypal` | "Approval did not complete within 120s (stuck at 'password')" |
| Step 19 | store order #1049 shown as Cancelled |
| Capture | none, so no order was captured |
| Step 24 | a second `pay_with_paypal` was refused: payment was already attempted in this run |

Every completed purchase so far ran locally.

### Live site check (same day)

| What | Value |
|---|---|
| API latency, warm | 0.6 to 1.0 s |
| `POST /api/runs` | 202 in 0.88 s |
| `/api/catalog` | 2.6 s |

### Local server in the hosted configuration, runs 60 and 61 (2026-11-12)

The server ran with `PAYPAL_MODE=mock` as its default, like the hosted one, and each run was started through `POST /api/runs` with only `{"real_payment": true}`, the way a visitor starts one.

| Run | Setup | Outcome |
|---|---|---|
| 60 | before the fix: a real run always used Kernel | Kernel's cloud browser could not reach `localhost:8000` (`ERR_CONNECTION_REFUSED` three times), gave up after 4 steps. Led to the fix: only popup payments need Kernel's live view |
| 61 | after the fix: saved sandbox buyer (vault), local Chromium, Nemotron 3.5 Super VL 120B, flaws price_as_image and no_structured_data | purchased in 12 steps, 35 s. PayPal order 5K109393AM6709716, capture COMPLETED $24.00, fee $1.33, net $22.67, payment verified through the agent-only verify route. Store order #1079 Paid, 4 of 4 ID links ok, no mismatches. Readiness 65/100 (price as text 12, structured data 12, stock readable 4 lost) |

### Test suite (2026-11-12)

Full run after the audit fixes, `pytest -q`: 657 tests, 646 passed, 11 failed, 779.5 s. The 11 failures were test setups only: 10 started a run on a server with no LLM (now a 400 `RUN_CONFIG` by design) and 1 listed the health keys without the new `vault_ready`. After fixing them, `test_budget.py` and `test_server_hardening.py` pass (59 passed, 63.8 s). Frontend `npm run build` passes.
