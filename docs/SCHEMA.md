# SQLite schema

There's one file at `DATABASE_PATH` (default `data/ghostshopper.db`). Timestamps are ISO-8601 UTC strings, and money is a decimal string like "24.00", never a float. The source of truth is `backend/app/db.py` (`SCHEMA` and `ADDED_COLUMNS`), `store/flaws.py`, `backend/app/eval/saboteur.py` and `backend/app/eval/judge.py`.

Everything is redacted for secrets before it's written (`agent/recorder.py`). Columns added after a table first shipped are added to older databases by `init_db`.

## store_flaws
| field | type | notes |
|---|---|---|
| key | TEXT PK | one of the 10 flaws in `store/flaws.py` |
| enabled | INTEGER | 1 = flaw on. The 4 classic flaws default to 1, the newer 6 to 0. |

## orders
| field | type | notes |
|---|---|---|
| order_id | TEXT PK | PayPal order id (`MOCK...` in mock mode) |
| sku, quantity | TEXT, INTEGER | |
| currency, amount | TEXT | priced on the server (the price_mismatch flaw adds $3.00 per item) |
| status | TEXT | CREATED, then COMPLETED |
| capture_id, capture_status | TEXT | from the capture response |
| gross_amount, paypal_fee, net_amount | TEXT | from `seller_receivable_breakdown` |
| created_at, captured_at | TEXT | |
| capture_response | TEXT | raw JSON, used by verification |
| run_id | INTEGER | the run that bought it; null for manual purchases |
| refund_id | TEXT | PayPal refund id, set once the test payment is refunded |
| refund_status | TEXT | COMPLETED, PENDING, CANCELLED or FAILED |
| refund_amount, refund_currency | TEXT | what PayPal says it returned |
| refunded_at | TEXT | |

## runs
| field | type | notes |
|---|---|---|
| id | INTEGER PK | |
| started_at, finished_at | TEXT | |
| status | TEXT | running, awaiting_human, completed, error |
| browser | TEXT | local or kernel |
| store_url, goal, target_product | TEXT | |
| checkout | INTEGER | 1 = the run includes payment |
| paypal_mode | TEXT | off, mock, sandbox |
| flaws_snapshot | TEXT | JSON of store_flaws when the run started |
| budget | TEXT | the shopper's spending limit in USD, like "30.00"; null = no limit. Enforced in code, not by the LLM |
| product_snapshot | TEXT | JSON of what the shopper read on the product page (Product JSON-LD, price text, image, stock). The product feed is built from it |
| llm, model | TEXT | mock, groq or scripted; the model id or cassette name |
| outcome | TEXT | purchased, reached_checkout, blocked, gave_up, error (decided from checks) |
| end_reason | TEXT | finished, agent_gave_up, agent_loop, step_limit, step_timeouts, error |
| agent_summary, agent_report | TEXT | what the LLM said, including its claimed outcome. Never scored. |
| step_count | INTEGER | |
| order_id | TEXT | the linked order |
| awaiting | TEXT | JSON while waiting for a human: stage, reason, since, timeout, Kernel live view URL |
| paypal_readiness | TEXT | JSON: PayPal setup checklist, recommendations and the 0-100 PayPal readiness figure (`agent/paypal_readiness.py`). Separate from the score. |
| error | TEXT | |
| owner_hash | TEXT | SHA-256 of the browser's owner token. NULL = shared example (made by the CLI or seed). `unclaimed` = made before checks had owners; hidden from the web, kept for the CLI. |

## steps
| field | type | notes |
|---|---|---|
| id | INTEGER PK | |
| run_id, idx | INTEGER | |
| tool, args | TEXT | tool name and JSON args |
| thought | TEXT | the LLM's text with the call |
| observation | TEXT | what the tool returned to the LLM |
| ok | INTEGER | 0 = the tool errored or timed out |
| url | TEXT | the page after the step |
| screenshot_path | TEXT | `runs/run-<id>/step-NN.png` |
| duration_ms, created_at | | |

## checks
One row per check per run (`UNIQUE(run_id, check_key)`; the first outcome wins). The score is computed from this table and nothing else.

| field | type | notes |
|---|---|---|
| id | INTEGER PK | |
| run_id, step_id | INTEGER | the step that produced it (null for end-of-run checks) |
| check_key, stage, severity | TEXT | from `scoring.CHECKS` |
| passed | INTEGER | 1 pass, 0 fail, NULL not tested |
| code | TEXT | failure type from `failures.FAILURE_TYPES` |
| cause | TEXT | store or environment; environment means it's excluded from the score |
| reason | TEXT | readable explanation |
| evidence | TEXT | JSON: url, selector, screenshot, snippet, order details |
| fix | TEXT | the LLM's rewording of the fix; never scored |

`failures` is a view: `SELECT * FROM checks WHERE passed IS NOT 1` (failed and untested).

## scores
| field | type | notes |
|---|---|---|
| run_id | INTEGER PK | |
| total | INTEGER | 0-100 over `possible` |
| possible | INTEGER | 100 minus the points excluded as not the store's fault |
| discover, details, checkout, payment, outcome | INTEGER | points earned per stage (max 5/40/30/20/5) |
| breakdown | TEXT | JSON fix list, most points first |
| excluded | TEXT | JSON list of excluded checks |
| rules_version | TEXT | `scoring.RULES_VERSION` |

## vault_tokens
The sandbox buyer's saved PayPal account (Vault v3), created once by `python -m backend.app.vault`. The payment token is secret-ish: it is never sent to the LLM and is redacted in run logs.

| field | type | notes |
|---|---|---|
| id | INTEGER PK | the newest row per mode is used |
| paypal_mode | TEXT | sandbox or mock; a token only works in the mode that made it |
| payment_token_id | TEXT | the Vault payment token id, sent only to the store's `/api/paypal/agent-orders` |
| customer_id | TEXT | PayPal's customer id for the token |
| created_at | TEXT | |

## Indexes and pragmas
Every connection (the store's too) sets WAL, `synchronous=NORMAL` and a 5000 ms busy timeout. Indexes, all created idempotently in `db.py`:

| index | columns | serves |
|---|---|---|
| idx_runs_owner_store_id | runs(owner_hash, store_url, id) | a browser's list and the before and after lookup |
| idx_runs_started_at | runs(started_at) | retention purge and ordering |
| idx_steps_run_idx | steps(run_id, idx) | a run's steps in order |
| idx_orders_run | orders(run_id) | the order for a run |

## flaw_proposals
LLM ideas for new flaws. They don't count in any benchmark until someone implements them as a toggle with a ground-truth label.

| field | type | notes |
|---|---|---|
| id | INTEGER PK | |
| key, description | TEXT | |
| expected_checks | TEXT | JSON list the LLM proposed |
| status | TEXT | implemented (already a labelled flaw) or proposed |
| source, created_at | TEXT | the model or cassette that proposed it |

## judge_ratings
LLM-as-judge ratings of fix explanations. This is a separate quality metric, and nothing in the scoring code reads it.

| field | type | notes |
|---|---|---|
| id | INTEGER PK | |
| run_id, check_key, code | | |
| matches_evidence, actionable | INTEGER | 1-5 |
| invented | INTEGER | 1 if the judge says something was made up |
| invented_numbers | TEXT | JSON: numbers in the explanation that aren't in the evidence |
| notes, judge_model, created_at | TEXT | |
| valid | INTEGER | 0 for a replayed cassette ("not valid until run live") |
