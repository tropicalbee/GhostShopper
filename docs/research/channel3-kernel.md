# Channel3 and Kernel research notes

Checked 2026-11-05. Both docs sites moved: Channel3 to https://channel3.ai/docs/, Kernel to https://www.kernel.sh/docs/.

## Channel3 (market check)
- Docs: https://channel3.ai/docs/ , search: https://channel3.ai/docs/api-reference/v1/search.md , SDK: https://channel3.ai/docs/sdk.md , limits: https://channel3.ai/docs/faq/rate-limits.md
- Base URL `https://api.trychannel3.com`, header `x-api-key`. Missing key: 401.
- `POST /v1/search`, body: `query` | `image_url` | `base64_image` | `page_token` (one required), `limit` (default 20, max 30), `filters` (default `conditions: ["new"]`, `availability: ["InStock"]`; `price: {min_price, max_price}`, brand/website/category ids, ...), `config` (`country`, `currency`, `mode`: keyword | default | agentic).
- Response `{products: [Product], next_page_token}`. Product: `id`, `title`, `brands[]`, `images[]`, `category`, `offers[]` with `url`, `domain`, `price: {price, compare_at_price, currency}`, `availability`, `condition`. There is no top-level price.
- Errors: 400, 401, 402 (out of free credits), 422, 429 (`Retry-After: 5`), 500, 504. Default plan 10 req/s, 10,000/day.
- Python SDK `channel3-sdk` (`from channel3_sdk import AsyncChannel3`; `client.products.search(query=...)`). We use httpx directly (no new dependency).
- Not verified: an example response verbatim, the free-credit amount.

## Kernel (hosted browsers)
- Docs: https://www.kernel.sh/docs/ , quickstart, `introduction/control.md` (Playwright over CDP), `browsers/live-view.md`, API reference (OpenAPI at https://api.onkernel.com/spec.json).
- REST: base `https://api.onkernel.com`, bearer auth (`Authorization: Bearer <KERNEL_API_KEY>`; header name inferred from the OpenAPI bearer scheme).
- `POST /browsers` body: `headless` (default false), `stealth` (default false; enables the CAPTCHA solver, we keep it false), `timeout_seconds` (default 60, 10-259200), `viewport`, `kiosk_mode`, `region`, `profile`, `proxy`, ... Returns `session_id`, `cdp_ws_url`, `browser_live_view_url` (non-headless only), ...
- Connect: `playwright.chromium.connect_over_cdp(cdp_ws_url)`, then `browser.contexts[0].pages[0]`.
- Delete: `DELETE /browsers/{id_or_name}` (204; 404 if gone).
- Live view: open `browser_live_view_url` to watch or interact (used for human approval); `?readOnly=true` for view-only. Invalid once the browser is deleted.
- Python SDK `kernel` (`from kernel import Kernel`; `kernel.browsers.create(timeout_seconds=...)`, `delete_by_id`). We use httpx directly; SDK keyword names other than `timeout_seconds`/`kiosk_mode` were not verified.
