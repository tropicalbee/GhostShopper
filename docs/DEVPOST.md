# Devpost description

Tagline: See your store through an AI shopper's eyes.

## Inspiration

PayPal showed that structured WebMCP tools cut an agent's shopping journey from 30+ interface steps to three tool calls in its test storefront. Structured tools only fix the browsing half. If the store's back end never marks the order paid, a WebMCP purchase breaks just like a browser one. PayPal's Store Sync docs say it "lets customers place orders directly into your existing order management systems", and we wanted to check that the order actually lands there correctly. PayPal's Agentic Commerce Pulse Report (498 US merchants, Q1 2026) also found that only about 1 in 5 merchants have 80% or more of their catalog as machine-readable data, and that data security is the top barrier.

## What it does

Paid, but your store doesn't know. In a live PayPal Sandbox run on our demo store, with a deliberate store bug switched on, an AI shopper paid $24.00 through a saved PayPal account. PayPal's capture came back COMPLETED ($1.33 fee, $22.67 net), but the store's own order, #1071, still said Awaiting payment. GhostShopper flagged the store order as the first mismatch. All four ID links held, and readiness was 65/100 (run 50, Nemotron 3.5 Lightning). With every flaw fixed (run 51) it scored 100/100 and order #1072 was Paid.

GhostShopper sends an AI shopper through the storefront and shows where the purchase breaks, with a screenshot, the element and the reason for each failure. It then reruns the purchase through PayPal Sandbox and checks that the intended purchase, the PayPal order, the capture and the store's order all agree.

It also runs the same purchase through WebMCP tools and checks both paths against the same five-record trace. On the same flawed store, the browser agent (run 57) took 10 steps and the WebMCP shopper (run 54) made 4 tool calls. PayPal captured $24.00 in both, and both ended with the store order still Awaiting payment. On PayPal's own showcase (run 56) the shopper bought a $25.00 gift card through PayPal's real tools, labelled as an external demo. The shopper can also look at a store page with a vision model when the text fails: in run 59, with the price only in an image, it read $24.00 from the screenshot and bought, and the readiness score stayed 65/100 because other agents need that price as text. A catalog readiness figure measures how much of a store's catalog is machine-readable, the 80% line from the Pulse Report.

A payment can succeed while the store's order is wrong: captured but still pending, marked paid after a decline, duplicated on a retry. GhostShopper links the records by ID and flags each broken link. It got all 33 deterministic trace scenarios right (mock PayPal, demo store).

Earlier live runs on the 120B Nemotron model went from 49/100 with five agent-facing failures (run 31) to 100/100 with a completed purchase verified against the store's order (run 34, $24.00 captured, $22.67 net). In run 52 a review hid a message aimed at AI agents. GhostShopper flagged it and the shopper did not follow it. The merchant also gets a fix list ordered by points and a before/after comparison. Market context for the product (similar listings and a median price) comes from Channel3. A live check on the hosted site on 2026-11-12 found 18 similar mugs, median $20.13, against our $24.00. Recorded responses are the labelled fallback. It is not reliable price intelligence.

The GhostShopper readiness score comes from our own deterministic checks. It is a diagnostic, not an Agent Ready, ACP or UCP conformance test, and not a PayPal certification. The WebMCP path gets an 8-item tool checklist computed by code, not a score. PayPal's own WebMCP needs enablement through Store Sync, which is a request form, and we could not get it for our demo store. So on Fernhill the WebMCP tools are our adapter for the same `shopping.*` tool contract PayPal's showcase registers, wired to our own Orders v2 sandbox checkout. The live results (65 to 100 in runs 50 and 51, 49 to 100 in runs 31 and 34) are from our demo store. The offline mock seed pair is 24 to 100.

A Vault agent payment path (saved PayPal vault id, idempotent request, spending limit, server-side capture) ran live in the PayPal Sandbox (runs 48, 50, 51 and 52). It is not the same as Agent Ready delegated payment tokens.

## How we built it

The shopper is a real tool-calling loop. NVIDIA Nemotron picks every step through an OpenAI-compatible endpoint (any such endpoint works; the recorded runs used Nemotron 120B for runs 31 to 37 and Nemotron 3.5 Lightning for runs 47 to 52), and Playwright runs the browser locally, and the WebMCP path uses Chromium's native WebMCP through the Chrome DevTools Protocol. Kernel can run the shopping journey in a hosted browser. A browse-only Shopify run in Kernel matched the local run (62/100, same five issues). We have not recorded a hosted Kernel purchase. After every step, code reads the page and records 19 checks, so the LLM never grades anything. Checkout uses the PayPal JS SDK v6 and Orders v2 create and capture in the sandbox. The backend is FastAPI with SQLite, and the dashboard is React, Vite and TypeScript with AG Grid Community. The demo store, Fernhill Ceramics, has 20 flaws we can switch on and off.

## Challenges

PayPal can show a CAPTCHA or an extra verification step. The agent doesn't touch it, and the run pauses as awaiting human approval. Kernel runs hung on sites with service workers until we fixed it. Store pages are untrusted, so the shopper treats page content as data and flags text aimed at AI agents.

## Accomplishments

33/33 deterministic trace scenarios passed (mock PayPal, demo store), with no false mismatches on healthy runs. Precision and recall were 1.0 on the benchmark of flaw combinations. Separately, live Sandbox purchases with all four ID links verified (runs 34, 50 and 51), including a captured payment the store still showed as Awaiting payment (run 50). The suite has over 500 tests, and the app is deployed at ghostshopper.onrender.com. We also ran the shopper on a public Shopify demo store, browse only, and it scored 62/100. That is a portability check, not validation.

## What we learned

A passing payment doesn't mean a correct order, so the records need comparing. The score and the trace answer different questions, and keeping the trace outside the score kept both honest.

## What's next

The full five record trace works on the demo store only, because real stores don't expose their order records yet. Next is working with real stores as they begin exposing those records.

## Built with

PayPal JS SDK v6, PayPal Orders v2 (sandbox), WebMCP (Chromium native, CDP), NVIDIA Nemotron, Kernel, Channel3, Playwright, FastAPI, SQLite, React, Vite, TypeScript, AG Grid Community.
