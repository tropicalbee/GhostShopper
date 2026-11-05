# SQLite schema

One file at `DATABASE_PATH` (default `data/ghostshopper.db`). Timestamps are ISO-8601 UTC strings. Money is a decimal string ("24.00"), never a float.

Status: **built** = exists in code; **planned** = design for its day.

## store_flaws (built, D1)

| field | type | notes |
|---|---|---|
| key | TEXT PK | `price_as_image`, `no_structured_data`, `ambiguous_buttons`, `extra_checkout_step` |
| enabled | INTEGER | 1 = flaw on. Defaults to 1 (bad store). |

## orders (built, D1)

| field | type | notes |
|---|---|---|
| order_id | TEXT PK | PayPal order id |
| sku, quantity | TEXT, INTEGER | what was bought |
| currency, amount | TEXT | amount computed server-side |
| status | TEXT | CREATED -> COMPLETED |
| created_at | TEXT | |
| capture_id, capture_status | TEXT | from capture response |
| gross_amount, paypal_fee, net_amount | TEXT | `seller_receivable_breakdown` |
| captured_at | TEXT | |
| capture_response | TEXT | raw JSON, evidence for D4 verification |
| run_id | INTEGER | **planned (D3)**: FK runs.id, null for manual purchases |

## runs (planned, D2)

| field | type | notes |
|---|---|---|
| id | INTEGER PK | |
| started_at, finished_at | TEXT | |
| status | TEXT | running, completed, error |
| browser | TEXT | local, kernel |
| store_url | TEXT | |
| goal | TEXT | e.g. "Buy one Speckled Stoneware Mug" |
| flaws_snapshot | TEXT | JSON of store_flaws at run start |
| model | TEXT | Groq model id |
| outcome | TEXT | purchased, blocked, gave_up, step_limit |
| error | TEXT | |

## steps (planned, D2)

| field | type | notes |
|---|---|---|
| id | INTEGER PK | |
| run_id | INTEGER | FK runs.id |
| idx | INTEGER | 0-based order |
| tool | TEXT | navigate, read_page, click, fill, ... |
| args | TEXT | JSON |
| observation | TEXT | truncated tool result |
| url | TEXT | page URL after the step |
| screenshot_path | TEXT | under `runs/` |
| duration_ms | INTEGER | |
| created_at | TEXT | |

## failures (planned, D2)

| field | type | notes |
|---|---|---|
| id | INTEGER PK | |
| run_id, step_id | INTEGER | FKs; step_id null for page-level checks |
| check_key | TEXT | e.g. `price_not_in_text`, `no_product_jsonld`, `ambiguous_cta`, `extra_step` |
| stage | TEXT | discover, details, checkout, payment |
| severity | TEXT | critical, major, minor |
| message | TEXT | human-readable |
| evidence | TEXT | JSON: url, selector, snippet, screenshot |
| fix | TEXT | LLM-written explanation (does not affect score) |

## scores (planned, D5)

| field | type | notes |
|---|---|---|
| run_id | INTEGER PK | FK runs.id |
| total | INTEGER | 0-100 |
| discover, details, checkout, payment | INTEGER | sub-scores |
| breakdown | TEXT | JSON: check_key -> points lost |
| rules_version | TEXT | scoring rules version, so reruns compare fairly |
