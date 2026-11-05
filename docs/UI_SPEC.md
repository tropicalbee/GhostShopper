# UI spec: GhostShopper

Two audiences. Small shopkeepers with little tech knowledge come first: they paste a link and want to know what to fix. Judges and technical users come second: they open the Advanced view for the evidence.

Style: the shadcn/ui look (ui.shadcn.com). Dark mode, zinc neutrals, rounded cards with subtle borders, Geist, generous spacing. One accent colour, used for score changes. Red only for failures the store caused. The demo store keeps its own plain look.

## Rules for every screen

- The Simple view has no jargon. It never says JSON-LD, selector, DOM or schema. Short sentences.
- Status colour always comes with words: "Ready for AI shoppers", "Some fixes needed", "AI shoppers will struggle to buy".
- The score label always says what it's out of: "How easily AI shoppers can buy from your store: 84% of what your store controls".
- Mock and fixture data always carries a visible label: "Practice run (scripted shopper, not AI)", "Mock PayPal", "Sample market data".
- Simple view: mobile first, works at 375px, tap targets at least 44px, no tables. Advanced view: desktop first (1280px and up); on a phone its failures become cards.
- Motion appears in two places only: the score counting from before to after, and new lines arriving in the step feed. Both turn off under `prefers-reduced-motion`.

## Screens

### 1. Home
- One question as the heading: "Can AI shoppers buy from your store?"
- One link box ("Your store's web address") and one button: "Check my store".
- A small text link under it: "Or try our demo store". That runs the demo store, which is the only place a real (sandbox) PayPal purchase happens.
- One line about safety: "We look around like a shopper. On your store we never buy anything or log in."
- Errors from `POST /api/runs` (400) appear under the box in plain words, e.g. "We couldn't find that website. Check the address for typos."
- Data: `POST /api/runs {store_url}` and `GET /api/health` (agent type and mock labels).

### 2. Live check
- Heading: "Checking your store…" with the store's address.
- A plain-language step feed from `run.feed`, polled every second: "Opened your home page", "Found your Speckled Stoneware Mug", "Couldn't read the price". Good lines get a check mark, problems a warning sign, and notes for things that aren't the store's fault an info sign, always with words.
- New lines slide in (the signature motion). Under reduced motion they just appear.
- The awaiting-human banner (demo store only) explains what PayPal is asking for and where to do it.
- When the run finishes, the screen moves to Results on its own.
- Data: `GET /api/runs/{id}` (`status`, `feed`, `awaiting`).

### 3. Results (Simple view, the default)
- The big score with its label and status, from `scorecard.simple`.
- Platform line when known: "Your store runs on Shopify", so the fixes make sense.
- For live stores, a note: "We checked up to your PayPal button and stopped. We never pay on real stores."
- The top 3 fixes as cards. Each has what's wrong, why it costs sales (one sentence), how to fix it (platform steps when we know the platform), and a "Show me" button that opens the screenshot in a dialog.
- "+ N more fixes" opens the Advanced view.
- Buttons: "Send to my developer" (a dialog with the copyable summary from `GET /api/runs/{id}/developer-summary`) and "Check my store again".
- "Not your store's fault" appears as a short note when there is something to say (e.g. the site's security check blocked us).
- Data: `GET /api/runs/{id}`.

### 4. Before and after (the demo centrepiece)
- The old score and the new score side by side. The new one counts up from the old one (the signature motion).
- "+51" in the accent colour.
- Two lists: "Fixed" (struck through, with a check mark) and "Still to fix" (each with its plain fix).
- The store changes and whether a purchase went through.
- Data: `GET /api/runs/compare?before=&after=` (defaults to the last two runs).

### 5. Advanced view (a toggle on Results)
- Tabs: Failures, Agent steps, Market, Not the store's fault.
- Failures: an AG Grid Community table (check, cause, points, evidence thumbnail, selector, technical fix), themed dark to match. On a phone it becomes cards.
- Agent steps: each step with its screenshot, tool, thought and observation.
- Market: Channel3 results with the "Sample market data" label when `source` is `recorded`.
- Not the store's fault, plus "Not checked on live stores" for live runs.
- Scoring details: the stage bars, the rules version, and the points the store controls.

## States

| State | What shows |
|---|---|
| Loading | Skeleton cards in the final layout |
| Link can't be checked | The plain 400 message under the link box; the box keeps its text |
| Check already running | "A check is already running. Try again when it finishes." |
| Site blocked us | Results with "We couldn't check your store this time" and why. Not the store's fault. |
| No runs yet (Before/after) | "Run a check, make your fixes, and check again to see the difference." |
| API down | "GhostShopper isn't responding" with a Retry button |
