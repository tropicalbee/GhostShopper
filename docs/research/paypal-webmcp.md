# PayPal WebMCP: links and notes

What we read about PayPal's WebMCP and how GhostShopper uses it. Observed on 2026-11-12 on PayPal's showcase unless a link says otherwise.

## Links

- Showcase store: https://webmcp-store.paypal.com/merchants/gift-cards?sdk=v6
- PayPal blog, WebMCP and Agent Ready: https://developer.paypal.com/community/blog/WebMCP_PayPal_Agent_Ready
- Agentic Commerce Pulse Report: https://www.paypal.com/us/brc/article/agentic-commerce-pulse-report-findings
- Agentic Commerce Services overview: https://developer.paypal.com/agentic-commerce-services/about
- Store Sync: https://developer.paypal.com/store-sync/overview

## Access

PayPal's WebMCP (their SDK script and their service) needs PayPal enablement through Store Sync. Store Sync is request-form only, per the Agentic Commerce Services overview (updated Oct 14 2026). We could not get it for our demo store. On the showcase, GhostShopper uses PayPal's real tools and service and labels the run "externally demonstrated, not GhostShopper-integrated". On Fernhill the tools are our own adapter for the same contract.

## What the showcase page loads

- PayPal web-sdk v6 core.
- PayPal's WebMCP script, `/webmcp/webmcp.v1.min.js`, with a `data-store-id` and a signed storefront-context token. The token is bound to the origin, so it cannot be reused on another site. We did not try.
- Tools are registered on `document.modelContext`, `navigator.modelContext` or `navigator.modelContextTesting`.
- The script calls PayPal's service with a JSON-RPC style `POST /rpc` and a body of `{jsonrpc, id, tool, input}`.
- Results use the envelope `{content, structuredContent}`.
- Buyer approval opens a popup window named `paypal-webmcp-approval`.

## The four tools

| Tool | Input |
|---|---|
| `shopping.searchProducts` | `query`, `max_results`, `category` |
| `shopping.getProduct` | `product_id` |
| `shopping.initiateCheckout` | `product_id`, `quantity`, `buyer_email`, `requires_user_approval` (our adapter's schema); returns an approval URL |
| `shopping.completeCheckout` | `cart_id`, `token`, after the buyer approves |

Our adapter registers the same names, schemas, result envelope and approval hand-off. The exact schemas are in `store/static/webmcp.js` and `backend/app/webmcp/rpc.py`.

## Browser side

- Chrome flags: `chrome://flags/#enable-webmcp-testing` and `#enable-webmcp`.
- `--enable-features=WebMCP` works in Chromium 156 (Playwright's bundled Chromium), so a script can launch it without touching flags.
- Chrome DevTools Protocol WebMCP domain: `WebMCP.enable` and the `WebMCP.toolsAdded` event to discover tools, `WebMCP.invokeTool` to call one and `WebMCP.toolResponded` for the result. GhostShopper uses these. A JS shim that records `registerTool` calls is only the fallback for browsers without native WebMCP.

## Numbers from PayPal

- The blog compares 3 tool calls with 30+ page steps and about 4.6x less inference cost. PayPal gives this as directional, from its test storefront.
- The Pulse Report surveyed 498 US merchants in Q1 2026. Only about 1 in 5 had 80% or more of their catalog as structured, machine-readable data, and data security was the top barrier. GhostShopper's catalog readiness figure measures that 80% line.
- Store Sync docs say it "lets customers place orders directly into your existing order management systems". GhostShopper checks that the order lands there correctly.

## Our runs on this

Runs 54, 56 and 57 are in [METRICS.md](../METRICS.md). Native discovery also found 12 WebMCP tools on `sauce-demo.myshopify.com`, a store we did not build.
