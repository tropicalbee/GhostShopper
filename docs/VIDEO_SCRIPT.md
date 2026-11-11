# Video script (2:35, AI voiceover, screen only)

Style: a YC product demo. Problem in one breath, then the real product on screen, then the result. No face, no music, no third-party store or brand other than the sponsors. Every number below comes from a recorded run (31 and 34 in METRICS.md).

Voice: an AI voice reading at a calm pace, about 150 words a minute. The voiceover is about 360 words.

Speed: agent footage runs at 4x to 8x with a small "4x" label in a corner. Cut every loading screen.

## Script

| Time | On screen | Voiceover |
|---|---|---|
| 0:00-0:08 | Black, then the Fernhill Ceramics product page fills the screen. | "This mug costs twenty-four dollars. A person can buy it in about twenty seconds." |
| 0:08-0:18 | The GhostShopper live view starts: the agent's browser on the left, the step feed on the right. | "Now an AI shopping agent tries the same store. It reads the page the way an agent does, and it decides every click itself." |
| 0:18-0:30 | Agent at 4x: it searches for the price, clicks "Continue", then "Go", then hits the details form. | "The price is a picture, so it can't read it. Three buttons say Continue, Proceed and Go. A form it didn't expect stands in front of checkout." |
| 0:30-0:42 | Title card, white text on black: "GhostShopper. A mystery shopper for the AI agent era." Then the landing page. | "AI agents are starting to shop for people. In PayPal's own test, an agent with structured tools bought in three calls. Without them, it took more than thirty steps through the page. GhostShopper shows small merchants on PayPal what that page looks like to an agent." |
| 0:42-1:05 | Results page of the bad store: score 49, the AG Grid failures table, one row expanded with its screenshot and fix. | "Twenty steps later, the store scores forty-nine out of a hundred. Every failure has the screenshot the agent saw, the element it got stuck on, and a fix written for the merchant. The score comes from code that checks each page. The AI never grades itself." |
| 1:05-1:15 | The fix list, ordered by points. | "Fixes are ranked by how much they're worth. Put the price in text. Add product data. Use one clear Buy button. Drop the extra form." |
| 1:15-1:25 | `/store/admin`: untick the four flaws. Save. | "The merchant applies the fixes." |
| 1:25-1:50 | Rerun at 4x: product page, Buy now, checkout, the PayPal button, the PayPal Sandbox popup, approve, the order page. | "Same agent, same rules. Eleven steps. It finds the mug, reads the price, and pays through PayPal: the real JavaScript SDK and the Orders API, in the Sandbox." |
| 1:50-2:15 | The purchase trace printing line by line: agent wanted, store order, PayPal order, PayPal capture, store says. Then "4 of 4 IDs linked". Hold on it. | "Here's the part payments teams care about. A payment can go through while the store's own order is wrong. Captured but still pending, or charged twice on a retry. GhostShopper links the store order, the PayPal order and the capture by their IDs and checks that they agree. All four links match. Twenty-four dollars captured, twenty-two sixty-seven net." |
| 2:15-2:25 | Before/after view: 49 to 100. Then a two-second pass over the market check panel. | "Forty-nine to a hundred, with the sale verified. Channel3 adds similar listings for context." |
| 2:25-2:35 | The hosted URL in the address bar, then the GitHub page. | "Nemotron drives the agent, Kernel runs the browser in the cloud, and it's live on Render. It's open source. GhostShopper: see your store through an AI shopper's eyes." |

## What each section earns

- 0:00 to 0:30 shows the problem working on screen before any explanation (Presentation, Potential Impact).
- 0:42 to 1:15 shows the AI and the deterministic checks (Technological Implementation, Design).
- 1:50 to 2:15 is the payments idea no other auditor has (Innovation, Best Use of PayPal + AI).
- The AG Grid table, Channel3, Kernel and Render each appear once, so the sponsor prizes can see them.

## Recording checklist

- [ ] Fresh state: `python -m backend.app.seed`, so the classic flaws are on.
- [ ] Record the bad-store run and the fixed-store run, both with the real PayPal Sandbox. Use the hosted site if a test run there works end to end. Otherwise record locally with `--headed` and show the hosted URL only in the closing shot.
- [ ] Browser at 1920x1080, zoom 110%, bookmarks bar hidden, no other tabs.
- [ ] Sandbox login typed by the agent only. Never show the buyer password or the `.env` file.
- [ ] Generate the voiceover from the text column, one clip per row, so a timing fix means one clip.
- [ ] Upload to YouTube as Public at least 2 hours before the deadline (12:00 PT, Nov 12). Paste the link into the README `<!-- VIDEO_URL -->` marker and the Devpost form.

## Backup

If the live sandbox fails on the day, `python -m backend.app.seed --with-runs` against a mock server records a before/after pair (24 to 100). Say in the voiceover that the payment is the practice PayPal, and keep the real trace numbers out of it.
