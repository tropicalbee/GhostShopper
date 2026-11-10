# UI spec: GhostShopper

Two audiences. Small shopkeepers come first: they paste a link and want to know what to fix. Judges and technical users come second: they open the Advanced view for the evidence. The approved designs are HTML mockups in `design/mockups/` (landing, new-check, live, results). Build from them; this file says what they leave out.

## Look

Black and monochrome, in the spirit of the vercel.com dark homepage but with our own motif: the receipt. GhostShopper proves a purchase, so the trace prints like a till receipt and the logo is a ghost whose hem is a torn receipt edge.

- Black page (#000), text #ededed, muted #a1a1a1, faint #8f8f8f, hairlines #1a1a1a to #2e2e2e. No other colours. No red, green or amber anywhere.
- Status shows by contrast. A mismatch or a failed check gets an outlined bright chip, a softly lit cell, or an inverted pill ("First mismatch", white on black). Normal values stay grey. Status still always comes with words.
- Geist for text and Geist Mono for data (money, ids, points, timings), loaded from the installed `@fontsource-variable` packages, never from Google Fonts.
- Surfaces are "glass" panels: near-black gradient fill, a 1px gradient border that is brighter at the top, a faint top sheen, 14px radius. No flat bordered boxes, no boxes inside boxes.
- Icons are lucide (`lucide-react`, already installed), 1.75 stroke, always next to a word.
- Buttons: one white primary per area, dark outlined secondary. Pills on the landing, 8px radius in the app.
- Headings stay modest: hero about 58px, section heads about 44px, app page titles about 30px.

## Motion

Keep it calm and quick. Allowed: the hero receipt printing once on load, the dashed stage path flowing slowly, the score counting up, new steps sliding into the live feed, receipt lines printing on the Live screen, a shine on white buttons and a small lift on cards when hovered, and the "What it catches" cards animating only while hovered. Not allowed: cursor spotlights, lights travelling along lines or borders, pulsing nodes, blur-in reveals. Everything turns off under `prefers-reduced-motion`. Use CSS; add Magic UI components through the shadcn CLI only when a plain CSS version is clearly worse.

## Routes

| Route | Screen |
|---|---|
| `#/` | Landing (no app bar) |
| `#/new` | New check. `#/new?store=yours` opens with "Your store" picked |
| `#/run/{id}` | Live while the run is running or awaiting a human, then Results |
| `#/run/{id}/advanced`, `#/run/{id}/compare`, `#/checks`, `#/ledger` | As today, restyled |

Landing buttons: "Run a check on the demo store" and the nav's "Run the demo" start a demo run (`POST /api/runs {}`) and open `#/run/{id}`. "Check your own store" opens `#/new?store=yours`. The paste box at the bottom starts a run with that link and opens it. App pages share one app bar: logo, tabs (New check, My checks, Sales ledger, Advanced), a "Practice mode" chip when PayPal is mocked, and on phones a menu button that opens the tabs in a sheet.

## Screens

Landing. Hero with the tagline, both buttons and the printing receipt; the five stages on a dashed path; three spine sections (the shopper's steps, the money, what the store says); the score section with the segment ring and the receipt-style sum; "What it catches" with five flaws; the paste box; a footer with a torn-receipt top edge. Copy comes from the mockup. The numbers on the landing are an illustration and say "Practice mode".

New check. Store choice (demo or your store). Demo shows the fixed product, payment mode (practice or sandbox) and the store problems from `GET /store/admin/flaws.json`, grouped into "Where the agent gets stuck" and "Where the purchase breaks". Your store shows the link box and the browse-only note. Start check posts `/api/runs` and opens the run. Errors from the API show under the field that caused them.

Live. Title with the product, a running timer, the step count and the practice chip; a Stop button. The latest real screenshot in a browser frame with the store's URL. The step feed from `run.feed`, newest first, steps that cost points marked with their fix. On the right, the trace receipt filling in as stages become known, and a "So far" count. The awaiting-human notice when `run.status` is `awaiting_human`. Polls once a second.

Results. Title says what happened to the purchase in one sentence, from the trace and the outcome. Then a four-part summary (purchase, money, readiness, shopper), the purchase trace table, the readiness score next to the money panel, and the shopper's path as a strip of real step screenshots (`GET /api/runs/{id}/files/{name}`). Before/after and the remaining sections stay below, restyled.

Advanced, Before/after, My checks, Sales ledger, Send to my developer. Same layouts and data as now, moved onto the black theme. AG Grid gets a dark theme built from the same tokens.

## The purchase trace

Data from `run.trace` (built by the backend, see TRD.md). Five columns in order: Agent wanted, Store order, PayPal order, PayPal capture, Store says. Five rows: product, quantity, amount, currency, status. Each column head shows its source (step, order number, PayPal id). A cell is a value, Unknown (with the reason under it), n/a (with the reason) or Not reached. Only the first mismatch is lit, and its explanation, fix and evidence links sit directly under the status row. On phones the table scrolls sideways inside its panel with a "Swipe to see all five records" hint, and the explanation moves under the table. The trace never changes the readiness score.

## Rules for every screen

- Short sentences and everyday words. The Simple view never says JSON-LD, selector, DOM or schema.
- Mock or recorded data always carries a visible label: "Practice mode: mock PayPal", "Sample market data".
- Works from 360px to 1920px with no sideways page scroll; tap targets at least 44px on phones.
- States as before: skeletons shaped like the final layout, the plain API error under the field, "We couldn't find that check.", "GhostShopper isn't responding" with Retry.
