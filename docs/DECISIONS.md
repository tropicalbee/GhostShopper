# Decisions

## 2026-11-05

- **PayPal JS Web SDK v6**, not v5. v6 is current; v5 is security-fixes only. Client-ID auth (no client token), per the set-up docs. Rejected: v5 `sdk/js?client-id=` (deprecated).
- **Sandbox hardcoded.** `PAYPAL_API_BASE` and SDK URL are constants, no env switch. Rejected: `PAYPAL_ENV` toggle (invites a live misconfig).
- **One FastAPI process serves API + store** (store is a mounted sub-app). One Render free service, same origin for the PayPal button's API calls, no CORS. Rejected: separate store service (two cold starts, CORS, more deploy work).
- **Store is server-rendered Jinja2**, not React. Flaws must exist in the HTML an agent fetches (JSON-LD present or absent server-side). Also keeps it plain, like a real small-merchant site.
- **Server prices orders from `store/products.json`.** The browser sends SKU + quantity only.
- **Capture only orders we created** (checked in SQLite), and validate the order id format.
- **Flaws default ON** so a fresh deploy is the "bad store" for the demo. Toggles stored in SQLite (`store_flaws`), editable by form or JSON.
- **Price image drawn as SVG line segments, no `<text>`,** with an opaque file name, so neither the DOM, the SVG source nor the URL leaks the price.
- **Store checkout is quantity 1.** Backend accepts 1-10. Scope lock: one product flow.
- **No auth on `/store/admin`.** Demo control panel; no accounts per scope lock. Risk: anyone with the hosted URL can toggle flaws.
- **Docs set:** CLAUDE.md DOCS section is canonical. `BUILD_LOG.md` is replaced by `issues-and-fixes.md`, `TODO.md` by `PLAN.md` checkboxes. Kept `DECISIONS.md`, `METRICS.md`, `CHANGELOG.md` (needed for submission).
