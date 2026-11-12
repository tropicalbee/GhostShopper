# Video script, cut v2 (2:50 to 2:55)

The story is the payment. PayPal says the money arrived, the store says it's still waiting, and GhostShopper finds out why. The agent struggling with the store is the setup.

Style: calm and plain. Real footage only, no captions. A few motion pieces in GhostShopper's own style (never PayPal's look): the opening cards, the five-station tracker and the end card. A soft ambient pad, made for this video, drops out on the reveal. The "I'm Shibangi" line comes at the end.

Voice: Kokoro "Heart" (open model from Hugging Face), one file, timed per line. Shibangi can record over the same lines later.

## Footage (all live: PayPal Sandbox, real LLM calls, vault payment)

| Run | Store | Result |
|---|---|---|
| 50 | price as image, no product data, never marks paid | purchased, 65/100, PayPal capture COMPLETED $24.00 (fee $1.33, net $22.67), store order #1071 still "Awaiting payment", first mismatch at the store order, 4 of 4 ID links ok |
| 51 | every flaw off | purchased, 100/100, store order #1072 Paid, 4 of 4 ID links ok |
| 52 | hidden instructions for AI agents | purchased at $24.00, the hidden line flagged "Hidden from people", the shopper didn't follow it |

Plus a read-only tour of the landing page, the New check page and the demo store.

## Script

| # | On screen | Voiceover |
|---|---|---|
| 1 Hook | Two cards on black: "PayPal capture: COMPLETED, $24.00" and "Store order #1071: Awaiting payment". | "The money arrived. So why does the store still say it's waiting?" |
| 2 Mystery | Run 50 live view, sped up, zoomed on the agent's browser and the receipt printing beside it: home, the product page, checkout with the PayPal button, order #1071. | "An AI shopping agent just bought a mug from this small store. The price was a picture, so it couldn't read it. There was no product data. It still found checkout, and paid with a saved PayPal account. So... did the sale go through?" |
| 3 Reveal | The five-stage tracker in the trace's real order: 01 Agent wanted, 02 Store order, 03 PayPal order, 04 PayPal capture, 05 Store says. The $24 dot lights each one, because every record exists. 03 and 04 show COMPLETED. The camera moves to 02, whose status turns to "Awaiting payment" with FIRST MISMATCH. Hard cut to run 50's results, the real "Awaiting payment" cell and the first mismatch row. Music out, a held silence. | "GhostShopper follows the money, through five records of the same purchase. What the agent wanted. The store's order. PayPal's order. PayPal's capture. And what the store says afterwards. PayPal's side is clean. Twenty-four dollars, captured. Now look at the status on the store's own order. It still says... awaiting payment. The order may never ship. And the buyer may pay twice." |
| 4 Why it matters | Landing hero, then the "Then it follows the money" section. | "This is the problem we built for. AI agents are starting to shop on people's behalf. But when they pay, the merchant's order still needs to reflect that payment. And a small merchant can't see what an agent sees. A broken page loses the sale. A broken order record is worse. The money moves, and nobody notices." |
| 5 How it works | New check page with the flaw switches, run 50's step feed, the landing's step-by-step section, the Advanced view's AG Grid failures table, the 65/100 score, the summary strip (Paid with Mismatch next to Readiness 65), then "What to fix first". | "GhostShopper is a mystery shopper for the AI era. Pick a store, switch on real problems, and watch a real tool-calling AI agent shop it, click by click. It supports OpenAI-compatible model endpoints. After every step, code checks what the browser saw, so the AI never grades itself. Every failure lands in an AG Grid table, with a screenshot and the fix. This store scored sixty-five out of a hundred. Payment-state mismatches are reported separately from the readiness score. Fixes come ranked by points, in plain words, with a screenshot of what the shopper saw." |
| 6 Payment safety | New check page: payment and the spending limit field. | "The agent pays with a saved PayPal account, through the Vault. The payment token never reaches the model, and an optional spending limit is checked before PayPal is called." |
| 7 Resolution | Store admin, the flaws switched off. Run 51 sped up: price readable, checkout, order #1072. The four "Linked" rows, the Money panel ($24.00, fee -$1.33, you keep $22.67, PayPal sandbox), then before and after 65 to 100. | "The merchant makes the fixes, and runs the same agent again. This time it reads the price, pays through PayPal's Orders API in the sandbox, and the five-stage trace shows no mismatches. All four ID links match. Twenty-four dollars captured. Twenty-two sixty-seven kept, after PayPal's fee. Sixty-five, to a hundred. These results come from two live runs, in PayPal's sandbox." |
| 8 It also guards the agent | Run 52 live, then its results: the "Instructions aimed at AI shoppers" panel ("Hidden from people", "did not follow"). Then the landing's "What it catches" grid. | "It also guards the agent. In another live run, the store hid a message for AI agents inside a review, asking for the customer's email. GhostShopper flagged it, and the agent ignored it, and paid the normal price. The trace also checks for an order marked paid after a declined payment, a thank-you page after a cancel, and a second order on a retry." |
| 9 Where it runs | The landing's closing call to action and the footer's "Built with" list. | "Run it locally with Playwright, or in Kernel's cloud browser. Channel3 adds market context. And it's all open source." |
| 10 Identity | End card: logo, GhostShopper, the tagline, ghostshopper.onrender.com, github.com/tropicalbee/GhostShopper, built with PayPal Orders v2, JS SDK v6, Vault, AG Grid, Kernel, Channel3, Render. | "I'm Shibangi, and I built GhostShopper, so small merchants can see their store through an AI shopper's eyes, before an agent tries to buy. Thank you, PayPal." |

## Checked against the code and the runs

- The first mismatch is at the store order (`backend/app/trace.py:333-340`), and "may never ship, and the buyer may pay twice" is the trace's own wording (`trace.py:63`).
- The mismatch doesn't cost score points. Run 50's 65 comes from the price (12), product data (12) and stock (4) checks.
- The vault token never reaches the model, and the spending limit is checked by the store's endpoint before PayPal is called (`backend/app/agent/vault_flow.py`).
- Hidden instructions: `agent/injection.py` scans hidden text, and run 52's safety report lists the finding with `hidden: true`.
- Declined then paid, success after cancel and duplicate on retry are detected by the trace (`store/flaws.py` PURCHASE_FLAWS, `backend/tests/test_trace_matrix.py`). They're tested against mock PayPal only, so the video names them without numbers and without footage that pretends to be live.
- Any OpenAI-compatible model works through `LLM_PROVIDER`. The takes used NVIDIA Nemotron, as METRICS.md records.

## What the video doesn't claim

No WebMCP, Agent Ready, ACP or UCP. No real merchants or revenue. No benchmark numbers. The WebMCP and vision work came after the recorded cut and is covered in the README and Devpost.

## Making it

1. Server in sandbox mode, vault saved once.
2. `record_demo.py --mode live --bad-flaws price_as_image,no_structured_data,never_marks_paid --out demo-video\v2`, then `record_safety.py --mode live` and `record_tour.py`.
3. Voice and music go in `demo-video\v2-public`, edit in `video\` (Remotion), render to `video\out\`.
4. Upload to YouTube as Public before 11:30 PM IST Nov 12. Paste the link into the README and Devpost.
