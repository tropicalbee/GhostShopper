# Issues and fixes

What broke, why, and what we did about it. Newest first.

## 2026-11-06 (robustness pass)

### Two starts could both pass the "already running" check
The check and the lock were separated by an await, so two requests arriving together both saw a free slot. The lock is now taken with no await after the check and released when the run's task ends.

### A start that timed out still ran a check
The client got an error after 30 seconds, but the task kept going and later produced a check nobody asked for. A timed-out start now cancels its task.

### LLM clients were never closed
Start validation and explain built a client and dropped it. They close it now. `prepare()` also builds the payment handler before the LLM, so a payment error can't leave an open client behind.

### Anyone could rewrite an example's fix text
Explain on a shared example check was open to every visitor, so one person could replace the example's wording and spend the server's LLM quota. It answers 403 now.

### The admin token ended up in logs and history
Passing the token in the `/store/admin` URL put it in access logs and the browser history. The URL form is gone. The page shows a plain unlock form that posts to `/store/admin/unlock` and sets an httpOnly, SameSite=Strict cookie. The `X-Admin-Token` header still works.

### Concurrent writers could fail with "database is locked"
Each connection used the default journal mode and no wait for a busy database. Every connection, the store's included, now uses WAL, `synchronous=NORMAL` and a 5 second busy timeout.

### Ownership checks built the whole run
File, delete and explain loaded the full run payload to see who owned it. They read the owner column only now.

### The failures table drew huge or clipped rows
AG Grid sets each cell's line height to the row height, so wrapped text spread out. Every column now forces normal leading and the same top padding (`CELL` in `FailuresGrid.tsx`). The Technical fix column hides under 900px so Evidence stays in view.

## 2026-11-06 (the Ledger redesign)

### The failures table hid the evidence
Seven columns with minimum widths of about 1,245px sat in a 1,120px space, so every text cell was cut off and the Evidence column was off screen. The selector moved into the technical fix's tooltip and the developer report, and the table lists only real store issues, so its count matches the tab.

### "What the shopper did" ended before the purchase
It kept the first seven lines that weren't neutral, and four problem lines at the same step pushed out the payment. It now keeps the key moments and always the last line.

### The Live screen screenshot showed an empty feed
The capture ran before the first feed line arrived. Captures now wait for at least four lines.

### A favicon 404 on every page
The browser asks for `/favicon.ico`. The page now carries an inline SVG icon.

## 2026-11-06 (checks belong to a browser)

### Anyone could open anyone's check
Run ids count up from 1 and every run endpoint answered for any id, so changing the number in the link showed another store's results, screenshots and developer report. Runs now carry the hash of the starting browser's cookie token, and every endpoint returns 404 for a run that isn't yours or a shared example.

### "Before and after" showed the demo store to everyone
It compared the last two finished runs in the whole database, whoever ran them. It now compares a check with the previous check of the same store from the same browser.

### Public callers could change server state through developer options
`POST /api/runs` accepted `record` (writes a file on the server), `flaws` (changes the shared demo store) and the rest. A deployed server now refuses everything except `store_url`.

### Iframes and images on a checked page could reach internal addresses
The browser guard only checked main-page loads, so a hostile page could frame an internal address and our screenshot would show it. Every request's host is checked now, and every redirect hop of the server's own fetches too.

### Old runs would have turned public after the migration
A NULL owner means "shared example", and the new column starts as NULL. The migration marks existing runs `unclaimed` instead, which hides them from the web and keeps them out of the retention purge.

### The not-found screen said the server was down
The frontend matched the old error wording ("No such run"). It now checks the HTTP status.

## 2026-11-06 (dashboard)

### The stage bars showed full marks on a 49 run
The scorecard only sent points earned per stage, so the chart had nothing to compare them with and fell back to earned as the maximum. The scorecard now sends `stage_possible` (stage total minus excluded points).

### AG Grid rows didn't wrap and left a gap under the table
With `wrapText` and `autoHeight`, the grid measured row heights before the flex columns reached their final widths. Rows stayed short and the page kept the extra height. Cells are now one line at 44px with the full text in a tooltip.

### "Check my store again" shrank to a thin bar on phones
`flex-1` in a column layout sets the height basis to 0. It's `sm:flex-1` now, so it only grows in the desktop row.

### The gauge caption sat on top of the arc
The caption was positioned inside the half ring. It sits under the gauge now, and only the number stays inside.

## 2026-11-05 (Day 5 session)

### Cart detection swallowed the demo store's extra step
The new rule "a page under /checkout is checkout" matched the demo store's details form at `/store/checkout/details`. Checkout looked reached before the form, so no_extra_steps passed on the bad store and two end-to-end tests failed. Only the last path segment counts now: `/checkout` is checkout, `/checkout/details` isn't.

### The scripted navigator always started at /store/
On any other site that's a 404 page, and platform detection locked in "unknown" from it. Live runs now start at `/`, and detection keeps looking until a page shows its platform.

### A store without PayPal never reached checkout
The cart page had no payment button and wasn't titled "Checkout", so the missing PayPal button was never reported. Cart and checkout pages are now also recognised by their title ("Your cart") or path, and on live stores the PayPal check stays "not tested" if the cart is never reached.

### robots.txt refusals were silent on clicks
When a click led to a disallowed page, the browser blocked the load but the step still looked successful. The click tool now says the page wasn't opened and why.

### The decision page closed unanswered
The Impeccable decision page went away after its second round. I asked through the question tool instead.

## 2026-11-05 (tasks 1-11)

### The summary check outranked its own cause
With PayPal not rendering, the first fix on the scorecard was task_completed ("fix the failures above"), worth 5 points, ahead of the actual cause, paypal_button_found at 4. The ordering was points first. Now the outcome stage always sorts after the failures, and there's a unit test for it.

### Loop detection would have stopped legitimate exploration
Trying the ambiguous buttons one by one means going back to the product page and listing its controls again. Under the first version of the loop detector, that counted as the same action three times in eight steps and the run would have been stopped. We spotted it while writing the scripted navigator, before any run hit it. The window now resets whenever the page changes.

### Two bash heredocs wouldn't parse
Two long multi-file edit scripts failed with "unexpected EOF while looking for matching `''", and nothing was written. We redid both with the file tools.

### PowerShell piping added a BOM
Piping `python -m backend.app.eval judge` into another Python process from PowerShell prefixed a UTF-8 BOM, and `json.load` refused it. The judge itself had already run, so its ratings were saved twice. We left both rows, since nothing gets deleted, and re-ran the summary through bash.

### New checks changed the flawed-store scores
After adding the six new checks and reweighting, the classic bad store scored 29 instead of 20 in browse runs and 49 instead of 40 in checkout runs. It passes the new checks its flaws don't affect. That's expected, and the end-to-end tests now pin the new numbers with the arithmetic in a comment.

### Old tests assumed exactly four flaws and four product checks
Three tests compared whole dicts. These were spec changes rather than regressions, so we updated the tests to build the expected values from the flaw list.

## 2026-11-05 (Days 2-3)

### Playwright wanted to download browsers outside the workspace
By default, `playwright install` writes to `%LOCALAPPDATA%\ms-playwright`. We install and run with `PLAYWRIGHT_BROWSERS_PATH=0`, which keeps the browsers inside `.venv`, and `agent/browser.py` sets that by default. While the headless shell was still downloading, `PLAYWRIGHT_CHANNEL=chromium` ran the full build headless.

### The agent can't read `.env`
This is by design: the agent isn't allowed to see secrets. Groq status came from `/api/health` (`groq_configured`), which only reports whether a key is set. For the Day 2 runs we started the server with `PAYPAL_CLIENT_ID=" "` in the process environment, not in `.env`, so no page loaded the real PayPal SDK.

### Buy-button evidence selector was longer than the test expected
The test wanted `div.act.act-a`; the evidence held `div.product > div.product-info > div.actions > div.act.act-a`. The full path is better evidence, so the test now checks the suffix.

### `<paypal-button>` showed up with an empty label
`find_elements` printed `e4 paypal-button ''`, so an agent couldn't tell what the element was. `innerText` doesn't see into shadow DOM, which is where web components put their text. The name now falls back to the open shadow root's text, then to the tag name ("paypal button").

### The health test pinned the exact JSON
The Day 1 `test_health` broke once we added `groq_configured` and `paypal_mode`. It now checks the stable keys and the type of the new ones.

### The mock popup opens as about:blank first
We could have recorded the popup's URL and screenshot before the SDK pointed it at the PayPal page. The flow now waits for the popup to leave `about:blank` first.

### PowerShell `Remove-Item Env:...` was denied
The no-deletion rule covers it, and we didn't need it anyway: each shell call starts with a clean environment.

## 2026-11-05 (Day 1)

### pytest couldn't create temp dirs
Every test using `tmp_path` failed with `PermissionError: [WinError 5] Access is denied: ...\Temp\pytest-of-shiba`. This sandboxed Windows setup won't let pytest use its shared temp folder, but a fresh `tempfile.mkdtemp()` folder works. The root `conftest.py` overrides `tmp_path` to do that, and nothing is deleted automatically.

### A Jinja macro wasn't visible in child templates
We caught this before running anything: `price()` was defined in `base.html`, but templates that extend it can't call it. Child templates only override blocks; the parent's top-level macros aren't exported. The macro moved to `store/templates/_macros.html` and is imported with `{% from "_macros.html" import price with context %}`.

### Two test assertions were too strict
`"FH-MUG-01" not in html` failed because the SKU is in the buy URL, and `'class="act' not in html` matched `class="actions"`. The store was behaving correctly. The tests now look for the `SKU:` and `In stock` text, and for `'class="act '` with a trailing space.
