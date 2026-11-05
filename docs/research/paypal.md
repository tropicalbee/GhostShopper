# PayPal research notes

Checked 2026-11-05.

## Links
- v5 to v6 migration: https://developer.paypal.com/v5-v6
- SDK set-up: https://developer.paypal.com/sdk/js/set-up
- v6 PayPal checkout quick start: https://developer.paypal.com/docsai/payments/methods/paypal/sdk/js/v6/paypal-checkout
- Orders API standard checkout: https://developer.paypal.com/api/rest/integration/orders-api/api-use-cases/standard
- v6 sample repo: https://github.com/paypal-examples/v6-web-sdk-sample-integration
- SDK reference (not yet read): https://developer.paypal.com/sdk/js/reference

## JS SDK
- Current generation is v6 Web SDK. Sandbox script: `https://www.sandbox.paypal.com/web-sdk/v6/core`; live: `https://www.paypal.com/web-sdk/v6/core`. No finer version number is published; "v6" is the version.
- v5 (`/sdk/js?client-id=...`) is in maintenance: security fixes only.
- `window.paypal.createInstance({ clientId, components: ["paypal-payments"], pageType })`. Client ID is the recommended auth for one-time payments; a client token is required only for Fastlane.
- `findEligibleMethods({ currencyCode })` then `methods.isEligible("paypal")`.
- `createPayPalOneTimePaymentSession({ onApprove, onCancel, onError })`; `onApprove` receives `{ orderId }`.
- Markup: `<paypal-button type="pay" hidden>`; remove `hidden` when eligible.
- On click: `session.start({ presentationMode: "auto" }, createOrder())`. Pass the promise; don't await it first (breaks popup transient activation). It must resolve to `{ orderId }`.

## Orders v2
- Token: `POST /v1/oauth2/token`, basic auth, `grant_type=client_credentials`.
- Create: `POST /v2/checkout/orders`, `intent: CAPTURE`, `purchase_units[].items` + `amount.breakdown.item_total`. 201, status CREATED.
- Capture: `POST /v2/checkout/orders/{id}/capture`, empty body. Capture within 3 hours of creation.
- Capture fields: `purchase_units[0].payments.captures[0].id/status`, `seller_receivable_breakdown.gross_amount/paypal_fee/net_amount`.
- `PayPal-Request-Id` (idempotency) and `Prefer: return=representation` are used in our client; not shown on the pages above, from the general REST API reference. Re-check if PayPal rejects them.
