# Video script (under 3:00, voiceover, no face on camera)

Setup before recording: `python -m backend.app.seed` (bad store), server running in sandbox mode with real credentials, browser windows sized for capture. On the hosted server, open `/store/admin` once in the recording browser and type the `DEMO_ADMIN_TOKEN` into the unlock form, and start both runs from the same browser so the before and after pairs them. Record the screen and add the voiceover afterwards.

The video shows four things: the bad store's failures, the fixes, the rerun with the PayPal verified purchase and its trace, and about 10 seconds on a real third party store (browse only). The AG Grid failures table shows up on its own while we scroll the results. Channel3 gets about 3 seconds, Kernel one line.

| Time | On screen | Voiceover |
|---|---|---|
| 0:00-0:20 Problem | Fernhill Ceramics home page, then the product page. | "PayPal showed that structured tools cut an agent's shopping journey from 30 or more interface steps to three tool calls. Where those tools aren't available, agents have to navigate the ordinary storefront themselves. This store looks fine to a person. GhostShopper sends an AI shopper through it." |
| 0:20-1:10 The bad store scores 49 | Live check feed next to the browser. The agent can't read the price, tries "Continue", then "Go", hits the details form. Results: the failures table (AG Grid) with evidence screenshots and the top fixes. | "The shopper decides every click itself. The price is an image. Only one of four buttons buys, and a form blocks the way. Every failure is logged with a screenshot, the element and the reason. The fixes are ordered by how many points they're worth." |
| 1:10-1:40 The fixes | `/store/admin`: untick the flaws. | "The merchant applies the fixes: price as text, product data, a real Buy button, no extra step." |
| 1:40-2:30 Rerun and the verified purchase | The agent goes straight to checkout, PayPal popup, sandbox login, approve. Then the purchase trace: the records lined up where each exposes them, all four ID links verified, $24.00 captured, $22.67 net. A few seconds on the market check, with a line that Kernel can run the browser (a browse-only run matched local). | "Same shopper, same rules. This time it completes the purchase through PayPal Sandbox. GhostShopper compares the intended purchase, the PayPal order, the capture and the store's order wherever each exposes them, and they agree: $24.00 captured, $22.67 net. The store went from 49 to 100. A payment can succeed while the store's order is wrong, so the trace flags the first record that disagrees. Channel3 adds market context, and Kernel can run the browser." |
| 2:30-2:45 A real store | About 10 seconds of the Shopify demo store run, browse only: score and issues. | "We also pointed it at a public Shopify store. It browses only, no purchase, and still finds issues. That checks it isn't tied to our demo." |
| 2:45-2:58 Close | Dashboard score, then the tagline. | "The score comes from deterministic checks. It is not an Agent Ready or WebMCP test, and not a PayPal certification. GhostShopper: see your store through an AI shopper's eyes." |

## Shot checklist
- [ ] Seeded bad store (`python -m backend.app.seed`), `/api/health` shows `paypal_mode: sandbox`, `paypal_configured: true`
- [ ] Before run recorded live (`--llm live --flaws keep --checkout --paypal sandbox --headed`)
- [ ] After run recorded live (`--flaws off`)
- [ ] Trace view on the after run, and `python -m backend.app.agent.compare --last` or the dashboard view
- [ ] Shopify browse-only run (run 37) on screen for about 10 seconds
- [ ] Backup: `python -m backend.app.seed --with-runs` against a mock server gives a mock before/after (24 to 100) if live fails on the day; say it is mock if used
