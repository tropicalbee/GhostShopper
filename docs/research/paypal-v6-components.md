# PayPal v6 Web SDK: component names

Checked against PayPal's docs on 2026-11-07.

Sources:
- https://developer.paypal.com/sdk/js/set-up
- https://developer.paypal.com/sdk/js/reference
- https://developer.paypal.com/docsai/developer/how-to/sdk/js/v6/configuration
- https://developer.paypal.com/docsai/payments/methods/venmo/integrate
- https://developer.paypal.com/cards/standalone-payment-button
- https://developer.paypal.com/pay-later/integrate.md
- https://paypal.github.io/paypal-js/web-sdk-v6-reference/

createInstance components:
- `paypal-payments`: PayPal and Pay Later (default).
- `venmo-payments`: Venmo, US only. Needed separately for the Venmo button.
- `paypal-guest-payments`: guest card checkout.
- `paypal-messages`: Pay Later messaging.

Elements and sessions:
- `<paypal-button>` with `createPayPalOneTimePaymentSession`.
- `<venmo-button>` with `createVenmoOneTimePaymentSession`.
- `<paypal-pay-later-button>` with `createPayLaterOneTimePaymentSession`. The set-up guide and checkout guide use this tag; the reference page shows `paylater-button`. We use the first.
- `<paypal-basic-card-button>` inside `<paypal-basic-card-container>`, with `createPayPalGuestOneTimePaymentSession`.
- `<paypal-message>` with `createPayPalMessages().fetchContent(...)` and `element.setContent(content)`.

Eligibility: `findEligibleMethods({ currencyCode })` returns an object with `isEligible(name)`. Documented names: `paypal`, `venmo`, `paylater`, `credit`, `card` (guest card). The generated types list `basic_cards`, `paypal_pay_later`; the prose docs use the short names above.
