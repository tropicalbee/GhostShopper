# Devpost description

Tagline: See your store through an AI shopper's eyes.

## Inspiration

PayPal showed that structured WebMCP tools cut an agent's shopping journey from 30+ interface steps to three tool calls in its test storefront. Where those structured capabilities aren't available, agents must navigate the ordinary storefront themselves, and merchants have no way to see where that path breaks. PayPal is building agentic commerce through Agent Ready and Store Sync. We wanted merchants to diagnose their existing storefront and purchase flow before they pursue those integrations.

## What it does

GhostShopper sends an AI shopper through the storefront and shows where the purchase breaks, with a screenshot, the element and the reason for each failure. It then reruns the purchase through PayPal Sandbox and checks that the intended purchase, the PayPal order, the capture and the store's order all agree.

A payment can succeed while the store's order is wrong: captured but still pending, marked paid after a decline, duplicated on a retry. GhostShopper links the records by ID and flags each broken link. It got all 33 deterministic trace scenarios right (mock PayPal, demo store).

Our demo store scored 49/100 with five agent-facing failures. After fixing them it scored 100/100, the AI shopper completed a $24 PayPal Sandbox purchase, and GhostShopper verified the payment against the store's order ($24.00 captured, $22.67 net). The merchant also gets a fix list ordered by points and a before/after comparison. Channel3 adds market context for the product (similar listings and a median price), not reliable price intelligence.

The GhostShopper readiness score comes from our own deterministic checks. It is a diagnostic, not an Agent Ready, ACP, UCP or WebMCP conformance test, and not a PayPal certification. GhostShopper tests the ordinary storefront with a browser-driven agent, PayPal JS SDK v6 and Orders v2. The live 49 to 100 result is from our demo store. The offline mock seed pair is 24 to 100.

A Vault agent payment path (saved PayPal vault id, idempotent request, spending limit, server-side capture) is implemented and mock-tested, not live-validated. It is not the same as Agent Ready delegated payment tokens.

## How we built it

The shopper is a real tool-calling loop. NVIDIA Nemotron picks every step through an OpenAI-compatible endpoint (Groq also works), and Playwright runs the browser locally. Kernel can run the shopping journey in a hosted browser. A browse-only Shopify run in Kernel matched the local run (62/100, same five issues). We have not recorded a hosted Kernel purchase. After every step, code reads the page and records 19 checks, so the LLM never grades anything. Checkout uses the PayPal JS SDK v6 and Orders v2 create and capture in the sandbox. The backend is FastAPI with SQLite, and the dashboard is React, Vite and TypeScript with AG Grid Community. The demo store, Fernhill Ceramics, has 20 flaws we can switch on and off.

## Challenges

PayPal can show a CAPTCHA or an extra verification step. The agent doesn't touch it, and the run pauses as awaiting human approval. Kernel runs hung on sites with service workers until we fixed it. Store pages are untrusted, so the shopper treats page content as data and flags text aimed at AI agents.

## Accomplishments

33/33 deterministic trace scenarios passed (mock PayPal, demo store), with no false mismatches on healthy runs. Precision and recall were 1.0 on the benchmark of flaw combinations. Separately, one live Sandbox purchase with all four ID links verified (run 34). The suite has over 500 tests, and the app is deployed at ghostshopper.onrender.com. We also ran the shopper on a public Shopify demo store, browse only, and it scored 62/100. That is a portability check, not validation.

## What we learned

A passing payment doesn't mean a correct order, so the records need comparing. The score and the trace answer different questions, and keeping the trace outside the score kept both honest.

## What's next

The full five record trace works on the demo store only, because real stores don't expose their order records yet. Next is working with real stores as they begin exposing those records.

## Built with

PayPal JS SDK v6, PayPal Orders v2 (sandbox), NVIDIA Nemotron, Groq, Kernel, Channel3, Playwright, FastAPI, SQLite, React, Vite, TypeScript, AG Grid Community.
