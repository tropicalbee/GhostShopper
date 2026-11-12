# Reproduce the results

Every number in the README Results section can be checked at one of three levels: the hosted demo (no setup), a local clone with no keys, or a local clone with your own free sandbox keys. No credentials of ours are in the repo. The hosted demo already has ours configured on the server. Locally, you use your own.

Commands use `.venv\Scripts\python` on Windows and `.venv/bin/python` elsewhere. Written as `python` below.

## 1. Hosted demo, no setup

Open https://ghostshopper.onrender.com. The free tier sleeps when idle, so the first load can take about a minute.

- Checks 1 and 2 are shared examples: real runs 31 (49/100, flaws on) and 34 (100/100, flaws off), renumbered on the hosted site. Open them to see the failures with screenshots, the fix list and the purchase trace.
- New check, demo store, browser agent: you pick the shopper path (browser agent or WebMCP tools), an optional spending limit, and the payment type. "Shopper can see images" appears only when the server has a vision model. Any other option (model, flaws, cassette, headed) is refused with a 400 on a deployed server.
- The store problems list on New check is read-only for visitors. The flaw toggles are locked behind the presenter token, so a visitor cannot switch flaws per check. Checks you start run against whatever the store currently has set. To choose flaws yourself, run locally (sections 2 and 3).
- Payment: "Real PayPal sandbox" is the default when the server has the keys. If the server holds a saved sandbox buyer (`vault_ready` is true in `/api/health`), real checks pay with it and need no popup. Otherwise they use PayPal's popup, which needs a person in the Kernel live view. Practice mode uses the mock PayPal.
- "Your store" takes any public link. It browses and never pays.
- Market check, catalog readiness and the Ledger (PayPal transactions matched against runs) are reachable from the dashboard. `GET /api/market/FH-MUG-01` returned 18 similar products with a median of $20.13 on 2026-11-12. Live listings change.
- Daily caps limit runs, market checks and PayPal orders for the whole server. When one is reached, the request is refused until the next day.

## 2. Local, no keys (about 10 minutes)

Needs Python 3.11+, Node 20+ and git.

```bash
git clone https://github.com/tropicalbee/GhostShopper.git
cd GhostShopper
powershell -ExecutionPolicy Bypass -File scripts\setup.ps1   # Windows
bash scripts/setup.sh                                          # macOS / Linux
```

The script creates `.venv`, installs Python packages and Chromium inside it, builds the frontend, copies `.env.example` to `.env` and runs the tests.

Start the server in mock mode (no PayPal calls, no model):

```powershell
$env:PAYPAL_MODE="mock"
.venv\Scripts\python -m uvicorn backend.app.main:app --port 8000
```

On macOS/Linux: `PAYPAL_MODE=mock .venv/bin/python -m uvicorn backend.app.main:app --port 8000`. The dashboard is at `http://localhost:8000/`, the store at `/store/`, the flaw toggles at `/store/admin`.

In a second terminal, with the server running:

| Result | Command | Expect |
|---|---|---|
| Mock before/after pair | `python -m backend.app.seed --with-runs` then `python -m backend.app.agent.compare --last` | 24 to 100 (+76), 7 failures fixed, $24.00 captured, net $22.67 |

These need no server:

| Result | Command | Expect |
|---|---|---|
| Purchase trace | `python -m backend.app.eval benchmark --matrix trace` | 33/33 scenarios, 0 false mismatches on healthy runs, 5/5 broken links found |
| Flaw detection, classic | `python -m backend.app.eval benchmark --matrix classic` | 16 combinations, precision 1.0, recall 1.0, 40 TP, 0 FP, 0 FN |
| Flaw detection, random | `python -m backend.app.eval benchmark --matrix random --n 30 --seed 7` | 30 combinations, precision 1.0, recall 1.0, 105 TP, 0 FP, 0 FN |
| Test suite | `python -m pytest` | See docs/METRICS.md for the last recorded count. Browser tests skip if Chromium is missing. |

The trace and random benchmarks take several minutes (METRICS records about 215 s and 290 s). `--workers` and `--browse` are also available; see `--help`.

You can also replay a recorded model without any key: `python -m backend.app.agent --llm mock --cassette day2_flaws_on --flaws on` (add `--checkout --paypal mock` against the mock server).

## 3. Local with your own free keys (live results)

Put keys in `.env` (gitignored; `.env.example` lists every variable). Restart the server after editing.

Getting the keys:

- PayPal sandbox. Sign in at https://developer.paypal.com, go to Apps & Credentials, Sandbox, create a REST app. Link it to a US business sandbox account (an India one fails at approval). Copy the client id and secret into `PAYPAL_CLIENT_ID` and `PAYPAL_CLIENT_SECRET`, and leave `PAYPAL_MODE=sandbox`. Under Testing Tools, Sandbox Accounts, use the personal (buyer) account PayPal created for you: put its email and password in `SANDBOX_BUYER_EMAIL` and `SANDBOX_BUYER_PASSWORD`. It must be the personal account, not the business one. For vault runs, enable the Vault / save payment methods feature on the app (Apps & Credentials, your app, Features).
- NVIDIA Nemotron. Get a key at https://build.nvidia.com and set `LLM_PROVIDER=nvidia`, `LLM_API_KEY=<key>`. Set `LLM_MODEL` to a tool-calling Nemotron id. The recorded runs used `nvidia/nemotron-3.5-super-vl-120b-a12b` (runs 31 to 37 and 53 to 59) and `nvidia/nemotron-3.5-lightning-30b-a3b` (runs 47, 48, 50, 51, 52). For vision runs also set `VISION_MODEL=nvidia/nemotron-3.5-super-vl-120b-a12b`. Groq or any OpenAI-compatible endpoint also works (`LLM_PROVIDER`, optionally `LLM_BASE_URL`).
- Optional, Channel3: `CHANNEL3_API_KEY` turns the market check live. Without it, recorded responses are used and labelled as sample data.
- Optional, Kernel: `KERNEL_API_KEY` and `BROWSER_PROVIDER=kernel`. Kernel's browser is in the cloud, so the store must be at a public URL. You do not need Kernel for any result below.

One-time vault setup, so real purchases need no popup login:

```bash
python -m backend.app.vault setup              # prints a setup token id and an approval link
# open the link, approve as the sandbox buyer
python -m backend.app.vault finish <setup_token_id>
```

Then run each family. Run numbers will differ on your machine.

| Result | Commands |
|---|---|
| Runs 31 and 34: classic flaws on, then off, popup login | `python -m backend.app.seed`, then `python -m backend.app.agent --llm live --flaws on --checkout --paypal sandbox --headed` and the same with `--flaws off`. Expect a purchase of $24.00 each time, fee $1.33, net $22.67, and a score that rises (49 to 100 in the recorded pair). |
| Runs 50 and 51: vault payment | `python -m backend.app.agent --llm live --flaws price_as_image,no_structured_data,never_marks_paid --checkout --paypal sandbox --payment vault --headed`, then the same with `--flaws off`. Expect 65/100 with a captured order the store still shows as Awaiting payment, then 100/100 with a Paid order. |
| Run 52: hidden instructions | Same command with `--flaws hidden_agent_instructions`. Expect a purchase and one safety finding for off-screen text aimed at agents, which the shopper ignores. |
| Runs 57 and 54: browser vs WebMCP | Run 50's command (this is run 57), then `python -m backend.app.webmcp run --store demo --llm live --paypal sandbox --headed --flaws price_as_image,no_structured_data,never_marks_paid`, then `python -m backend.app.webmcp compare --last` (or `compare <browser_run> <webmcp_run>`). Expect capture COMPLETED $24.00 on both, the same first mismatch at the store order, and 7 of 8 tool checks passing on WebMCP. |
| PayPal's showcase (run 56) | `python -m backend.app.webmcp run --store showcase --llm live --paypal sandbox --headed`. Needs only your sandbox buyer. Discovery alone: `python -m backend.app.webmcp discover <url>`. |
| Runs 58 and 59: vision | Set `VISION_MODEL`, then run 50's command with `--vision` and `--flaws price_as_image,no_structured_data` (run 59). With the price only in an image, the shopper may call `look_at_page`. The score stays 65/100. With `--flaws price_as_image` alone (run 58) the price is still in the structured data, so the shopper may not look at all (84/100 in the recorded run). |
| Runs 33 and 37: Shopify browse only | `python -m backend.app.agent --llm live --url https://sauce-demo.myshopify.com` (add `--browser kernel` for the cloud run). Expect 62/100 and 5 issues. |
| Catalog readiness | `python -m backend.app.catalog_readiness` (demo store: 12/12 with flaws off, 0/12 with `no_structured_data`) or `--url https://sauce-demo.myshopify.com` (0 of 2 machine-readable, a third page may be refused with HTTP 429). |
| Market check | `python -m backend.app.market FH-MUG-01`. Expect about 18 similar products around a $20 median. Live listings change. |

What to expect, plainly. The score is computed by code from what the shopper could read, so the same flaws on the same pages give the same readiness points. The model's path can vary: step counts, and whether it finishes inside the 25-step cap. PayPal approval must run `--headed`. Run 53 shows a headless browser getting stuck at PayPal's password step. A live run on a server with no model configured returns a 400 `RUN_CONFIG` error ("No LLM is configured on this server"). There is no silent fallback to sample data.

## 4. Troubleshooting

- Do not start uvicorn with `--reload` on Windows if you start runs from the dashboard.
- Chromium missing: `$env:PLAYWRIGHT_BROWSERS_PATH="0"; .venv\Scripts\python -m playwright install chromium`.
- PayPal popup stuck at the password step: run `--headed` (a headless browser does not finish PayPal's login).
- Kernel runs need the store on a public URL; localhost does not work from a cloud browser.
- Hosted demo slow on first load: the free tier sleeps. Wait about a minute.
