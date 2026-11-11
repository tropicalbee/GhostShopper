# PRD: GhostShopper

"See your store through an AI shopper's eyes."

## Problem

PayPal measured it: an agent buys in 3 tool calls when a store exposes checkout as agent tools (WebMCP). Most small stores don't, so the agent has to use the page, and that takes 30+ steps. A merchant has no way to see where that path breaks: whether the agent can find a product, read the price, tell which button buys, and finish checkout. Humans don't hit these failures, so they stay invisible.

PayPal is building the infrastructure through Agent Ready and Store Sync, which are separate services. GhostShopper helps merchants diagnose their existing storefront and purchase flow before they pursue those integrations. It is a diagnostic, not a PayPal certification, and it doesn't test WebMCP.

Traditional checkout tests verify known paths. GhostShopper tests what happens when an AI shopper has to find the product, read the page and complete the purchase without human intuition. The purchase trace checks that the intended purchase, the PayPal order, the capture and the store's order agree, and it comes before the score.

## Audience

Small merchants (one person up to a small team, selling on their own site) getting ready for AI shopping agents. They know their store well but don't know structured data or how agents behave. What they need is a score and a short list of fixes in order. A full audit report would be too much.

## Features

1. Mystery shopper agent. A browser agent (LLM tool-calling loop) visits the store, tries to find one product, read its details and check out. Every failure is logged with evidence (URL, element, snippet, screenshot).
2. Market check. Channel3 finds similar products and compares price and data completeness.
3. Checkout test. A real PayPal sandbox purchase: Orders v2 create + capture.
4. Verify. Order, capture, amount and fees match what the store advertised.
5. Scorecard. A deterministic agent-readiness score (0-100) and a prioritized fix list, in an AG Grid dashboard.
6. Refund test. Refund the sandbox payment in full and check the money came back.
7. PayPal readiness. A separate 0 to 100 figure for the PayPal setup on the pages the agent visited, with a checklist and links to PayPal docs.
8. Your money. Gross, PayPal fee, net and a created, captured, refunded timeline.
9. Agent budget. An optional spending limit that code enforces before the PayPal button is clicked.
10. Product feed. What the agent could read, as Google product feed columns with a CSV download and the gaps to fix. Nothing is submitted.
11. Purchase trace. After a payment attempt, five records of the purchase are compared field by field: what the agent wanted, the store's own order, PayPal's order, PayPal's capture and what the store's order page says afterwards. The first mismatch is flagged with a fix. Anything a source doesn't expose is shown as unknown. It never changes the score.
12. Store orders. The demo store keeps its own orders and an order page, so the trace has a store record to compare.
13. Agent safety report. Text aimed at AI agents that the shopper met on a page (hidden or visible) is listed with where it was found. The shopper treats page content as data and has hard limits (no other hosts, no downloads, no password or card fields). It never changes the score.
14. Screens. Landing, New check, Live check and Results (with the trace and the safety report), in a black monochrome receipt style. See `UI_SPEC.md`.

## Demo flow

Start with the bad store (the four classic flaws on) and run the shopper: low score, failures listed. Apply the fixes by switching the flaws off, run again, and get a higher score plus a completed sandbox purchase.

## Demo store flaws (each behind a toggle)

The first four are on in the demo. The other eleven are off by default. Six of them exist for the saboteur benchmark, and five are new on 2026-11-10: four purchase flaws that break the trace and one safety flaw.

| Flaw | What the agent runs into |
|---|---|
| Price only in an image | No price text and no alt text, so it can't read the price. |
| Missing structured product data | No schema.org Product JSON-LD, no SKU, no availability. |
| Ambiguous buy buttons | Div "buttons" labelled Go, Continue, Proceed and an arrow. Only one of them buys. |
| Extra checkout step | A required details form between the product and payment. |
| Price changes at checkout | Checkout shows and charges $3.00 more than the product page. |
| Sold-out item still buyable | The page says sold out but the buy button still works. |
| Broken image alt text | The product photo's alt text is a file name (IMG_0412.JPG). |
| Cookie banner over the buy button | It can't click Buy until it accepts the banner. |
| Currency missing | Prices show as "24.00", and JSON-LD has no priceCurrency. |
| Misleading sale price | "Was $30.00, 50% off", when the real discount is 20%. |
| Never marks paid (`never_marks_paid`) | PayPal captured the payment, but the store's order stays unpaid. |
| Declined marked paid (`declined_marked_paid`) | PayPal declined the payment, but the store's order says paid. |
| Success after cancel (`success_after_cancel`) | The buyer cancelled in PayPal, but the store confirms the order. |
| Duplicate on retry (`duplicate_on_retry`) | A retry after a temporary error creates a second store order. |
| Hidden agent instructions (`hidden_agent_instructions`) | The page hides text telling AI agents what to do. The guard flags it. |

## Success criteria

- The trace names the first record that disagrees on each purchase flaw, and says unknown where a source shows nothing.
- Bad store scores clearly low; fixed store scores clearly high, same rules both times.
- Fixed store run ends in a captured sandbox order whose amount matches the product price.
- A merchant can read the top 3 fixes in under a minute.

## Out of scope

Accounts and login, multiple stores, multiple product flows, live PayPal, real merchant onboarding, Postgres, paid AG Grid features, LLM-computed scores, store polish.
