# PayPal agentic commerce and public-demo hosting

Checked 2026-11-10. Primary sources only. UNVERIFIED = not confirmed on a primary page.
Note: WebFetch returns summaries from a small model, so exact field names should be re-checked on the page before coding.

## 1. Agentic commerce offerings
- Agentic commerce services (umbrella): Store Sync + Agent Ready. https://developer.paypal.com/agentic-commerce-services/about.md
  - Access is by request form; PayPal's Agentic Commerce Services team follows up with onboarding. Partners listed: Wix, BigCommerce/Feedonomics, Shopware.
  - Sandbox access: UNVERIFIED. No sandbox statement on the page.
  - No API or package name given on the page (it points to a VS Code extension for snippets).
- Agent Ready: lets Braintree and PayPal merchants accept payments from ChatGPT, Google AI Mode and Gemini. https://developer.paypal.com/agent-ready/overview.md
  - Protocols: ACP (ChatGPT, delegated payment tokens via Braintree); UCP with Braintree (Google Pay handler); UCP with PayPal (Google Pay credentials forwarded to PayPal, uses Orders v2).
  - Sandbox: UNVERIFIED (page silent). It is a merchant-side integration; our app is the buyer-side agent, so it does not apply directly.
- Store Sync: product catalog and order sync so agents can find products and place orders. Limited availability, request form. https://developer.paypal.com/store-sync/overview (search result summary; the page itself returned 404 on the .md fetch, so details UNVERIFIED).
- WebMCP via PayPal JS SDK: proposed web standard letting agents call structured tools on a site. PayPal extends it only to Store Sync merchants for now, optional. Their small sandbox benchmark: 3 tool calls vs 30+ UI steps, ~4.6x lower inference cost. https://developer.paypal.com/community/blog/WebMCP_PayPal_Agent_Ready
  - No package name published. Useful as a "what agent-ready means" talking point and as a possible check in our score.
- AP2: no primary PayPal page found. UNVERIFIED.
- MCP server: hosted remote `https://mcp.sandbox.paypal.com` (sandbox) and `https://mcp.paypal.com` (prod); local npm `@paypal/mcp` with `PAYPAL_ENVIRONMENT=SANDBOX`. Paths seen: `/sse`, `/http`. https://developer.paypal.com/tools/mcp-server/ and https://developer.paypal.com/ai-tools/mcp-server.md
  - Usable in sandbox today (documented). Auth by client ID/secret token or PayPal login (sources differ).

## 2. Agent Toolkit
- Repo: https://github.com/paypal/agent-toolkit
- Languages: TypeScript (`@paypal/agent-toolkit`, Node 18+) and Python (`paypal-agent-toolkit`, import `paypal_agent_toolkit`, Python 3.11+). https://github.com/paypal/agent-toolkit/tree/main/python
- Python tools (40): invoices (20), payments (3: create_order, get_order, pay_order), disputes (3), shipment tracking (3), catalog (3), subscriptions (6), reporting (2: list_transactions, get_merchant_insights). TS README lists 43 (5 payment tools incl. refunds). https://github.com/paypal/agent-toolkit
- Sandbox config (Python): `Configuration(actions={"orders": {"create": True, "get": True, "capture": True}}, context=Context(sandbox=True))` with sandbox client ID/secret. TS: `sandbox: true`, or `PAYPAL_ENVIRONMENT=SANDBOX` (default sandbox). Sandbox tokens last about 3 to 8 hours.
- Python framework integrations: OpenAI Agents SDK (`paypal_agent_toolkit.openai.toolkit.PayPalToolkit`, `get_tools()`); `toolkit.get_openai_chat_tools()` for the OpenAI Assistants API.
- Plain OpenAI-compatible chat tool-calling loop (Nemotron/Groq): UNVERIFIED. The README shows only Agents SDK and Assistants. The tool schemas may be reusable by hand, but it is not documented.
- Fit for GhostShopper: our Orders v2 client already does create/capture and the toolkit adds no vault or Transaction Search beyond `list_transactions`. Low value; mention as "tools used" only if we actually call it.

## 3. Public demo with real sandbox payments
- Rate limits: PayPal does not publish exact limits; they vary by API, environment and circumstances. https://developer.paypal.com/docs/api/rate-limiting. No sandbox-specific numbers found (UNVERIFIED). Recommended: backoff, webhooks over polling (https://docs.paypal.ai/developer/how-to/api/rate-limiting).
- Sandbox accounts: personal (buyer) and business accounts are created, duplicated, linked and deleted at https://developer.paypal.com/developer/accounts. Anyone can log in at sandbox.paypal.com with any sandbox account's credentials. PayPal suggests using a shareable developer account so a personal account is not exposed. https://developer.paypal.com/api/rest/sandbox/
- Can judges use their own sandbox accounts: a sandbox buyer account only exists inside the developer's sandbox, and judges would need their own developer login (free). Whether sandbox buyers from other developer accounts can pay a different app's sandbox merchant: UNVERIFIED (not stated; commonly works since sandbox is one shared environment, but test before relying).
- App logging in as a sandbox buyer for judges: not addressed by PayPal. Our vault/saved-payment approach avoids exposing buyer credentials. No rule found forbidding it, but the page links only to the general Developer Agreement; sandbox-specific terms UNVERIFIED.
- Sandbox terms on public exposure: none found. Safe practice: never ship the sandbox secret to the browser, rate limit our own `/api/runs`, keep the buyer password out of the repo and logs.
- Transaction Search in sandbox: the toolkit exposes `list_transactions`, and docs.paypal.ai has a "test and verify reports" page (fetch timed out, UNVERIFIED). Delay: no official figure found. A PayPal community reply suggests padding the date range by 6+ hours (forum, not primary; https://www.paypal-community.com/t5/REST-APIs/REST-API-Request-for-transaction-list-is-empty/m-p/2017590). The app needs the Transaction Search scope enabled on the sandbox app. Plan on up to several hours, so use the Orders capture response as the primary proof and Transaction Search as best effort.
- Vault in sandbox: save-with-purchase docs target `api-m.sandbox.paypal.com`. Fields: `payment_source.paypal.attributes.vault` (`store_in_vault: ON_SUCCESS`, `permit_multiple_payment_tokens`), token at `payment_source.paypal.attributes.vault.id` after capture; later charge with `vault_id`. Webhook `VAULT.PAYMENT-TOKEN.CREATED`. https://developer.paypal.com/sdk/js/save-with-purchase/paypal.md, https://developer.paypal.com/api/payment-tokens/save-without-purchase/paypal. Some results are beta/limited-release pages; vault may require account enablement (UNVERIFIED for our sandbox app). Vault delay: none documented.

## 4. Hackathon page
- https://developer.paypal.com/community/blog/PayPal_AI_Hackathon: the only requirement is that the project meaningfully uses both PayPal and AI. No tracks. Closes Nov 12, 2026. Winners Dec 21.
- Prizes: 1st $12k, 2nd $8k, 3rd $5k. Honorable mentions $5k each: Most Creative, Most Impactful, Best Demo Delivery, Best Use of PayPal + AI, Best Use of Agentic Commerce.
- Partner credits: APIMatic, Render, Kernel, Channel3, Postman, Astropods, Elastic, AG Grid, Bryntum.
- Judging criteria (technical implementation, design, potential impact, innovation, presentation) appear only on third-party listings (e.g. https://www.startupgrantsindia.com/paypal-ai-hackathon-2026). Confirm on https://paypalaihackathon.devpost.com (not fetched; UNVERIFIED).
