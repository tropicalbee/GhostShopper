# Video script (about 2:45, AI voiceover, screen only)

Style: a YC product demo. The problem in one breath, then the real product on screen, then the result. No face, quiet music under the voice, no third-party store or brand other than the sponsors. Every number below comes from the video take of Nov 11: run 47 (bad store, 18) and run 48 (fixed store, 100), both on NVIDIA Nemotron 3.5 Lightning with real PayPal Sandbox calls. Runs 31 and 34 in METRICS.md tell the older 49 to 100 story on the 120B model.

Voice: Mako in Google AI Studio, recorded as one file (`demo-video/live/voice/Generated Audio November 12, 2026 - 2_56AM.wav`) and cut into `row01` to `row11` on word timestamps. The ending below is the user's recorded wording. Paste the voiceover text as it is. The tags in angle brackets are Mako expressions; leave them in for AI Studio and strip them for the Kokoro backup.

The edit lives in `video/` (Remotion). Rows run longer when their clip needs more time, so a timing fix only means a new clip.

## Script

| Time | On screen | Voiceover |
|---|---|---|
| 0:00-0:08 | The Fernhill Ceramics product page, the camera eases in on the price. | "This mug costs twenty-four dollars. A person can buy it in about twenty seconds. Can an AI agent?" |
| 0:08-0:18 | The GhostShopper live view starts: the agent's browser and its step feed. | "Here's an AI shopping agent on the same store. It reads the page the way an agent does, and it decides every click itself." |
| 0:18-0:30 | The agent sped up, going round in circles between the mug, another product and the newsletter page. | "The price is a picture, so it can't read it. It clicks Continue and lands on a different product. Proceed opens a newsletter. The real buy button just says Go. <breath> After twenty-five steps, it gives up." |
| 0:30-0:52 | The landing page with the PayPal benchmark caption, the title card, then a card with two questions: "Can an AI agent buy from your store?" and "Does the payment match the order?" | "AI agents are starting to shop for people. On PayPal's own test storefront, structured tools let an agent buy in three calls instead of thirty-plus page steps. Most small stores don't have those tools, so agents use the page. And reaching checkout is only half the job. The payment also has to match the merchant's order. GhostShopper tests both." |
| 0:52-1:15 | Results of the bad store: score 18, then the AG Grid failures table, labelled in a caption. | "Eighteen out of a hundred. In this run the agent never reached checkout, so nothing was paid. The score comes from code that checks each page. The AI never grades itself. Every failure lands in an AG Grid table, ranked by points, with what the agent saw, the fix for the merchant, and a screenshot." |
| 1:15-1:25 | The fix list, ordered by points. | "Fixes are ranked by how much they're worth. Put the price in text. Add product data and stock status. Use one clear Buy button." |
| 1:25-1:35 | `/store/admin`: untick the four flaws, save. | "The merchant applies the fixes." |
| 1:35-2:00 | The rerun, sped up: product page, Buy now, checkout, paid. | "Same agent, same rules. Eleven steps. It finds the mug, reads the price, and pays with the buyer's saved PayPal account. Real Orders API calls in the PayPal Sandbox, with no popup and no password." |
| 2:00-2:25 | The purchase trace, then the ID links. | "<breath> But a captured payment doesn't prove the order is right. A store can take the money and still show the order as pending, or charge twice on a retry. GhostShopper links the store order, the PayPal order and the capture by their IDs, and checks that they agree. All four links match. Twenty-four dollars captured, twenty-two sixty-seven net." |
| 2:25-2:35 | Score card counting 18 up to 100, then a pass over the market check. | "Eighteen to a hundred, and the payment matches the order. Channel3 adds market context." |
| 2:35-2:47 | End card: tagline, hosted URL, GitHub, built with, and a thank-you to PayPal for the hackathon. | "From finding the product to verifying the payment, GhostShopper shows merchants where AI shopping works and where it breaks. GhostShopper: see your store through an AI shopper's eyes. Thank you, PayPal, for this opportunity." |

## What each section earns

- 0:00 to 0:30 shows the problem on screen before any explanation (Presentation, Potential Impact).
- 0:30 to 0:52 states the PayPal problem early: an agent purchase has two halves, buying and a payment that matches the order. The benchmark is PayPal's own small test, quoted as that and not as a general result. GhostShopper does not test WebMCP, so the video doesn't show or imply it.
- 0:52 to 1:25 shows the AI and the deterministic checks (Technological Implementation, Design).
- 1:35 to 2:25 is the agent paying with a saved PayPal account and the ID checks behind it (Innovation, Best Use of PayPal + AI).
- The AG Grid table, Channel3, Kernel and Render each appear once, so the sponsor prizes can see them.

## Making the video

1. Server: `PAYPAL_MODE=mock LLM_MODEL=nvidia/nemotron-3.5-lightning-30b-a3b .venv\Scripts\python -m uvicorn backend.app.main:app --port 8000`. The vault payment needs a saved sandbox buyer once (`python -m backend.app.vault setup`, then `finish`).
2. Take: `.venv\Scripts\python scripts\video\record_demo.py --mode live --out demo-video\live`. It writes `raw-demo.mp4` and `markers.json` (scenes and zoom targets).
3. Voice: clips go in `demo-video\live\voice\row01.wav` to `row11.wav` (mp3 or m4a work too). Music goes in `demo-video\live\music.mp3`.
4. Preview with `cd video && npm run studio`, render with `npm run render`. The mp4 lands in `video\out\`.
5. Upload to YouTube as Public at least 2 hours before the deadline (12:00 PT, Nov 12). Paste the link into the README `<!-- VIDEO_URL -->` marker and the Devpost form.

## Backup

`npm run studio:dry` previews the edit on the mock take in `demo-video\dry-run`. If a live take fails on the day, the mock take renders the same way; say in the voiceover that the payment is the practice PayPal, and leave the sandbox numbers out.
