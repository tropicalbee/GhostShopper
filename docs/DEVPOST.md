# Devpost description

Tagline: See your store through an AI shopper's eyes.

## Inspiration

PayPal measured it: an agent buys in 3 tool calls when a store exposes checkout as agent tools (WebMCP). Most small stores don't, so the agent has to use the page, and that takes 30+ steps. Merchants have no way to see where that page path breaks. PayPal is building agentic commerce through Agent Ready and Store Sync. We wanted merchants to diagnose their existing storefront and purchase flow before they pursue those integrations.

## What it does

GhostShopper sends an AI shopper through the storefront and shows where the purchase breaks, with a screenshot, the element and the reason for each failure. It then reruns the purchase through PayPal Sandbox and checks that the intended purchase, the PayPal order, the capture and the store's order all agree.

A payment can succeed while the store's order is wrong: captured but still pending, marked paid after a decline, duplicated on a retry. GhostShopper links the records by ID and flags each broken link. It caught all 33 trace scenarios in our benchmark.

In our demo store, the shopper struggled with a $24 purchase. After the fixes, it completed the purchase through PayPal Sandbox: $24.00 captured, $22.67 net, matched to the store's order. The merchant also gets a readiness score, a fix list ordered by points, and a before/after comparison. Channel3 adds market price context for the product.

The GhostShopper readiness score comes from our own deterministic checks. It is a diagnostic, not a PayPal certification or an Agent Ready eligibility check, and it doesn't test WebMCP. The 24 to 100 result is from our demo store.

## How we built it

The shopper is a real tool-calling loop. NVIDIA Nemotron picks every step through an OpenAI-compatible endpoint (Groq also works), and Playwright runs the browser locally. Kernel runs the shopping journey in a hosted browser. After every step, code reads the page and records 18 checks, so the LLM never grades anything. Checkout uses the PayPal JS SDK v6 and Orders v2 create and capture in the sandbox. The backend is FastAPI with SQLite, and the dashboard is React, Vite and TypeScript with AG Grid Community. The demo store, Fernhill Ceramics, has 20 flaws we can switch on and off.

## Challenges

PayPal can show a CAPTCHA or an extra verification step. The agent doesn't touch it, and the run pauses as awaiting human approval. Kernel runs hung on sites with service workers until we fixed it. Store pages are untrusted, so the shopper treats page content as data and flags text aimed at AI agents.

## Accomplishments

All 33 trace scenarios came out right, with no false mismatches on healthy runs. Precision and recall were 1.0 on the saboteur benchmark of flaw combinations. We have a live sandbox purchase where all four ID links were ok. We also ran the shopper on a public Shopify demo store, browse only, and it scored 62/100. That is a portability check, not validation.

## What we learned

A passing payment doesn't mean a correct order, so the records need comparing. The score and the trace answer different questions, and keeping the trace outside the score kept both honest.

## What's next

The full five record trace works on the demo store only, because real stores don't expose their order records yet. Next is working with real stores as they begin exposing those records.

## Built with

PayPal JS SDK v6, PayPal Orders v2 (sandbox), NVIDIA Nemotron, Groq, Kernel, Channel3, Playwright, FastAPI, SQLite, React, Vite, TypeScript, AG Grid Community.
