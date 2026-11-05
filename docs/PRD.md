# PRD: GhostShopper

"See your store through an AI shopper's eyes."

## Problem

PayPal wants small merchants to be discoverable and buyable by AI shopping agents (Agent Ready, Store Sync). A merchant has no way to see how an agent experiences their store: whether it can find a product, read the price, tell which button buys, and finish checkout. Failures are invisible because humans don't hit them.

## Audience

Small merchants (one-person to small-team shops on their own site) preparing for AI shopping agents. They know their store, not structured data or agent behavior. They need a score and a short, ordered list of fixes, not an audit report.

## Features

1. **Mystery shopper agent.** A browser agent (LLM tool-calling loop) visits the store, tries to find one product, read its details and check out. Every failure is logged with evidence (URL, element, snippet, screenshot).
2. **Market check.** Channel3 finds similar products and compares price and data completeness.
3. **Checkout test.** A real PayPal sandbox purchase: Orders v2 create + capture.
4. **Verify.** Order, capture, amount and fees match what the store advertised.
5. **Scorecard.** A deterministic agent-readiness score (0-100) and a prioritized fix list, in an AG Grid dashboard.

## Demo flow

Bad store (all four flaws on) -> run -> low score + failures -> apply fixes (toggle flaws off) -> rerun -> higher score + successful sandbox purchase.

## Demo store flaws (each behind a toggle)

| Flaw | What the agent hits |
|---|---|
| Price only in an image | No price text, no alt; the agent cannot read the price. |
| Missing structured product data | No schema.org Product JSON-LD, no SKU, no availability. |
| Ambiguous buy buttons | Div "buttons" labeled Go / Continue / Proceed / arrow; one buys. |
| Extra checkout step | Required details form between product and payment. |

## Success criteria

- Bad store scores clearly low; fixed store scores clearly high, same rules both times.
- Fixed store run ends in a captured sandbox order whose amount matches the product price.
- A merchant can read the top 3 fixes in under a minute.

## Out of scope

Accounts and login, multiple stores, multiple product flows, live PayPal, real merchant onboarding, Postgres, paid AG Grid features, LLM-computed scores, store polish.
