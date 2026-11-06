# PRD: GhostShopper

"See your store through an AI shopper's eyes."

## Problem

PayPal wants small merchants to be discoverable and buyable by AI shopping agents (Agent Ready, Store Sync). A merchant has no way to see how an agent experiences their store: whether it can find a product, read the price, tell which button buys, and finish checkout. Failures are invisible because humans don't hit them.

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

## Demo flow

Start with the bad store (the four classic flaws on) and run the shopper: low score, failures listed. Apply the fixes by switching the flaws off, run again, and get a higher score plus a completed sandbox purchase.

## Demo store flaws (each behind a toggle)

The first four are on in the demo. The other six are off by default and exist for the saboteur benchmark.

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

## Success criteria

- Bad store scores clearly low; fixed store scores clearly high, same rules both times.
- Fixed store run ends in a captured sandbox order whose amount matches the product price.
- A merchant can read the top 3 fixes in under a minute.

## Out of scope

Accounts and login, multiple stores, multiple product flows, live PayPal, real merchant onboarding, Postgres, paid AG Grid features, LLM-computed scores, store polish.
