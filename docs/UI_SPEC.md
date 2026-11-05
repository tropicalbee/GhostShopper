# UI spec: GhostShopper

Two audiences. Small shopkeepers with little tech knowledge come first: they paste a link and want to know what to fix. Judges and technical users come second: they open the Advanced view for the evidence.

The developer or web agency never logs in. They get the "Send to my developer" report. Checking many client stores in one place is a "what's next" line in the README. PayPal's platform view (how many merchants AI shoppers can't buy from, and the most common reason) is part of the pitch only: aggregated, opt-in, and not built.

## Look

"Ledger": a calm working screen in the spirit of ui.shadcn.com and the user's Razorpay Buildathon dashboard. No dark mode.

- White ground, hairline cool-grey rules, square corners. A 1.5px dark rule closes each page head and table head.
- Soft ink (#18181b) instead of pure black. The only dark fill on a screen is its one primary button. The score sits on a pale panel, never in a black block.
- Geist for text. Geist Mono only for data: the score, points, money, order ids and selectors.
- Colour carries meaning only: red for failures the store caused, green for good, amber for "some fixes needed". Status colour always comes with words.
- Region titles are small, muted and in sentence case. No all-caps labels.
- The signature is the shopper's path: the five stages as one strip, each as wide as the points it's worth, grey for points earned, hatched for points lost, and the plain reason in red under the stage where the shopper got stuck.
- Charts use Recharts (score history, market check). AG Grid Community is used for the failures table and nothing else.
- Keep it calm. A screen shows what the user needs for the next step and puts the rest behind a tab, a dialog or the Advanced view.

## Navigation

- Desktop: a left sidebar with New check, My checks, and the browser's six most recent checks (store, check number, date, score). When the demo store's settings are unlocked, a link to them sits at the bottom.
- Phone: a top bar with the GhostShopper mark and a menu button. The menu opens the same sidebar as a sheet from the left.

## Rules for every screen

- Written for someone who doesn't read much. Short sentences, everyday words, one idea per line. Every icon has a word next to it.
- The Simple view never says JSON-LD, selector, DOM or schema.
- Status colour always comes with words: "Ready for AI shoppers", "Some fixes needed", "AI shoppers will struggle to buy".
- The score label says what it's out of: "How easily AI shoppers can buy from your store", then "49% of what your store controls".
- Mock and fixture data always carries a visible label: "Practice run (scripted shopper, not AI)", "Mock PayPal", "Sample market data".
- Every screen works from 360px phones to 1920px screens with no sideways scrolling. Tap targets are at least 44px. The Advanced view opens from tablet width (768px); below that the toggle is hidden and its grid stacks.
- Motion in two places only: the score counting up from before to after, and new lines arriving in the step feed. Both turn off under `prefers-reduced-motion`.

## Screens

### 1. Home
- Heading: "Can AI shoppers buy from your store?"
- One link box ("Your store's web address") and one button: "Check my store".
- A small link under it: "Or try our demo store". The demo store is the only place a sandbox PayPal purchase happens.
- One line about safety: "We look around like a shopper. On your store we never buy anything or log in."
- Errors from `POST /api/runs` (400) show under the box in plain words, and the box keeps its text.
- Data: `POST /api/runs {store_url}`, `GET /api/health`.

### 2. Live check
- Heading: "Checking your store…" with the store's address.
- The shopper's path above the feed, filling stage by stage from the checks logged so far (stage points from `GET /api/rubric`).
- The step feed from `run.feed`, polled every second. Good lines get a check mark, problems a warning sign, things that aren't the store's fault an info sign, always with words.
- The awaiting-human banner (demo store only) says what PayPal is asking for and where to do it.
- When the run finishes, the screen moves to Results.
- Data: `GET /api/runs/{id}` (`status`, `feed`, `awaiting`).

### 3. Results, Simple view (the default)
One score, three fixes, one main button.
- The score panel: its label, the big number out of 100, the status line, and a compact shopper's path. On desktop it sits beside the fixes; on a phone it comes first.
- Platform line when known: "Your store runs on Shopify".
- For live stores: "We checked up to your PayPal button and stopped. We never pay on real stores."
- The top 3 fixes as cards: what's wrong, why it costs sales, how to fix it (platform steps when known), and a "Show me" button that opens the screenshot.
- "+ N more fixes" opens the Advanced view on desktop.
- Main button: "Check my store again". Secondary: "Send to my developer".
- "Not your store's fault" is a short note, only when there is something to say.

### 4. Send to my developer (dialog)
- The Markdown from `GET /api/runs/{id}/developer-summary` in a scroll box.
- Three buttons: "Copy", "Download" (a `.md` file) and "Email" (a `mailto:` link with the report in the body). No email is sent by GhostShopper.

### 5. Before and after (the demo centrepiece)
- Old score and new score side by side. The new one counts up from the old one.
- The change ("+51") in green.
- Two lists: "Fixed" with a check mark and "Still to fix" with its plain fix.
- Whether a purchase went through.
- Reached from a result's "See before and after", only when this browser has an earlier check of the same store. A demo store visitor who can't change the demo store gets "See an example before and after" instead.
- Data: `GET /api/runs/{id}/compare` (this check against the previous one of the same store from the same browser).

### 6. Advanced view (desktop, toggle on Results)
A ruled grid on top, tabs underneath.
- The grid: the score panel; the shopper's path with points per stage; what the shopper did (the feed's key lines); the payment check as a small ledger ending in "You receive", marked Verified or Not verified.
- Tabs: Failures (AG Grid: check, cause, points, evidence, selector, technical fix), Agent steps (screenshot, tool, thought), History (score across this store's checks, `GET /api/runs`), Market (Channel3 results, "Sample market data" when `source` is `recorded`), Not the store's fault (plus "Not checked on live stores" for live runs).
- The points the store controls sit under the score; the rules version sits at the foot of the page.

### 7. My checks (in the sidebar and the phone menu)
- This browser's checks, newest first: score, store, date. Tapping one opens its results.
- Each row has a Delete button with a confirm dialog ("Delete this check?", "Keep it" or "Delete").
- One line explains it: "Saved in this browser only. Other people can't see them." Under the list: how many days checks are kept, and that clearing cookies removes them from the list.
- Empty: "You haven't checked a store yet." with a "Check my store" button.
- Shared example checks show the label "Example check (shared demo, not yours)" and are never listed here.

## States

| State | What shows |
|---|---|
| Loading | Skeleton cards in the final layout |
| Link can't be checked | The plain 400 message under the link box |
| Check already running | "A check is already running. Try again when it finishes." |
| Site blocked us | Results with "We couldn't check your store this time" and why. Not the store's fault. |
| No runs yet (Before/after) | "Run a check, make your fixes, and check again to see the difference." |
| API down | "GhostShopper isn't responding" with a Retry button |
| Someone else's check, or a deleted one | "We couldn't find that check." and a link to My checks |
| Too many requests | "That's a lot of requests in a short time. Please wait a few minutes and try again." |
