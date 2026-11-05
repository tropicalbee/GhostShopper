# Video script (under 3:00)

Setup before recording: `python -m backend.app.seed` (bad store), server running in sandbox mode with real credentials, browser windows sized for capture. Shots marked [dashboard] need the Day 5 dashboard. Until it exists, film the CLI output and `/store/admin` instead.

| Time | On screen | Narration |
|---|---|---|
| 0:00-0:20 Problem | Fernhill Ceramics store home page, then a quick zoom on the product page. | "AI shopping agents are starting to buy things for people. PayPal is getting merchants ready for that. But a small shop has no way to see what an agent sees. This store looks fine to a human. Let's send an AI shopper in." |
| 0:20-1:00 Bad store run | Start a run (headed browser). The agent opens the store, finds the mug, reads the page, tries "Continue" (wrong product), comes back, tries "Go", hits the details form, fills it, reaches checkout. | "GhostShopper's mystery shopper is a real AI agent: it decides every click itself. It can't read a price, because the price is an image. The buttons say 'Continue', 'Proceed', 'Go', and only one of them buys. Then there's a form it has to fill before it can pay." |
| 1:00-1:30 Failures and score | [dashboard] Score 49/100, failures grid with evidence screenshots and selectors, fix list ordered by points. | "Every failure is logged with evidence: the screenshot, the exact element, and why. The score is computed by code from those checks, never by the AI. The fix list is ordered by impact: make the price text, add product data, use a real Buy button, remove the extra step." |
| 1:30-2:10 Fixes, rerun, higher score | `/store/admin`: untick the flaws. Rerun. The agent goes straight from product to checkout. [dashboard] Before/after: 49 -> 100, "5 failures fixed, 0 remaining". | "The merchant applies the fixes, and we run the same shopper again. This time it reads the price and the stock, clicks Buy now, and goes straight to checkout. The before-and-after shows exactly what changed: plus 51 points, five failures fixed, none left." |
| 2:10-2:40 PayPal sandbox purchase | The agent clicks the PayPal button, the PayPal popup opens, sandbox login, approve. Confirmation page with the order number. Then the verification: order, capture, $24.00, PayPal fee, net. | "Then it pays. A real PayPal sandbox checkout: JS SDK v6, Orders v2 create and capture. GhostShopper confirms the capture and checks that the order, the captured amount, the advertised price and PayPal's fees all add up. If PayPal asks for a human check, the agent stops and waits for a person to do it." |
| 2:40-3:00 Why it matters | Scorecard plus "not the store's fault" note, then the tagline. | "A PayPal merchant gets a score, the fixes that move it, and a real purchase showing an AI shopper can get all the way through. GhostShopper: see your store through an AI shopper's eyes." |

## Shot checklist
- [ ] Seeded bad store (`python -m backend.app.seed`), `/api/health` shows `paypal_mode: sandbox`, `paypal_configured: true`
- [ ] Before run recorded live (`--llm groq --flaws keep --checkout --paypal sandbox --headed`)
- [ ] After run recorded live (`--flaws off`)
- [ ] `python -m backend.app.agent.compare --last` (or the dashboard view)
- [ ] Sandbox merchant account shows the payment (optional cutaway)
- [ ] Backup: `python -m backend.app.seed --with-runs` against a mock server gives the same before/after on mocks if live fails on the day
