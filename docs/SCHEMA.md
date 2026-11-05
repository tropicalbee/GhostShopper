# SQLite schema

One file at `DATABASE_PATH` (default `data/ghostshopper.db`). Timestamps are ISO-8601 UTC strings. Money is a decimal string ("24.00"), never a float. Source of truth: `backend/app/db.py` (`SCHEMA`) and `store/flaws.py`.

All tables below are **built** (D1-D3). Secrets are redacted before every write (`agent/recorder.py`).

## store_flaws
| field | type | notes |
|---|---|---|
| key | TEXT PK | `price_as_image`, `no_structured_data`, `ambiguous_buttons`, `extra_checkout_step` |
| enabled | INTEGER | 1 = flaw on. Default 1 (bad store). |

## orders
| field | type | notes |
|---|---|---|
| order_id | TEXT PK | PayPal order id (`MOCK...` in mock mode) |
| sku, quantity | TEXT, INTEGER | |
| currency, amount | TEXT | computed server-side from the catalog |
| status | TEXT | CREATED -> COMPLETED |
| capture_id, capture_status | TEXT | from the capture response |
| gross_amount, paypal_fee, net_amount | TEXT | `seller_receivable_breakdown` |
| created_at, captured_at | TEXT | |
| capture_response | TEXT | raw JSON (D4 verification evidence) |
| run_id | INTEGER | set when an agent run bought it; null for manual purchases |

## runs
| field | type | notes |
|---|---|---|
| id | INTEGER PK | |
| started_at, finished_at | TEXT | |
| status | TEXT | running, completed, error |
| browser | TEXT | local (Kernel later) |
| store_url, goal, target_product | TEXT | |
| checkout | INTEGER | 1 = run includes payment |
| paypal_mode | TEXT | off, mock, sandbox |
| flaws_snapshot | TEXT | JSON of store_flaws at run start |
| llm, model | TEXT | mock / groq; model id or cassette name |
| outcome | TEXT | reached_checkout, purchased, blocked, gave_up, step_limit, error |
| agent_summary, agent_report | TEXT | what the LLM says (report = price/stock it read). Never scored. |
| step_count | INTEGER | |
| order_id | TEXT | linked order |
| error | TEXT | |

## steps
| field | type | notes |
|---|---|---|
| id | INTEGER PK | |
| run_id, idx | INTEGER | |
| tool, args | TEXT | tool name; JSON args |
| thought | TEXT | LLM text with the call |
| observation | TEXT | tool result shown to the LLM |
| ok | INTEGER | 0 = tool error |
| url | TEXT | page after the step |
| screenshot_path | TEXT | `runs/run-<id>/step-NN.png` |
| duration_ms, created_at | | |

## checks (replaces the planned `failures` table)
Every check outcome, pass or fail, one row per check per run (`UNIQUE(run_id, check_key)`, first outcome wins). The score is computed only from this table.

| field | type | notes |
|---|---|---|
| id | INTEGER PK | |
| run_id, step_id | INTEGER | step that produced it (null for end-of-run checks) |
| check_key, stage, severity | TEXT | from `scoring.CHECKS` |
| passed | INTEGER | 1 pass, 0 fail, NULL not tested |
| reason | TEXT | human-readable |
| evidence | TEXT | JSON: url, selector, screenshot, snippet / order details |
| fix | TEXT | LLM explanation (D5), never scored |

`failures` is a **view**: `SELECT * FROM checks WHERE passed IS NOT 1` (failed + not tested).

## scores
| field | type | notes |
|---|---|---|
| run_id | INTEGER PK | |
| total | INTEGER | 0-100 |
| discover, details, checkout, payment | INTEGER | points earned per stage (max 10/50/20/20) |
| breakdown | TEXT | JSON fix list, ordered by points recoverable |
| rules_version | TEXT | `scoring.RULES_VERSION` |
