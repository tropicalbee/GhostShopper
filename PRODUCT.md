# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

Small merchants who run their own online store and want AI shopping agents to be able to find and buy their products. They know their store well but don't know structured data or agent behaviour. The dashboard is a real merchant tool, but demo first: every scene of a three-minute hackathon video (recorded on a laptop, 1280px and up) has to read instantly to judges watching it.

## Product Purpose

GhostShopper sends an AI mystery shopper through the merchant's store, logs where it gets stuck with evidence, runs a real PayPal sandbox purchase, and turns all of that into a readiness score with a fix list. Success means the merchant sees what to fix, fixes it, reruns, and watches the score go up and a purchase go through.

## Positioning

The score comes from deterministic checks on what the browser actually saw, never from the LLM. Only failures the store causes cost points; a declined card or a blocked popup is shown separately as "not the store's fault". The proof is a real PayPal checkout, verified down to the fees.

## Operating Context

The merchant (or the presenter in the video) starts a run, watches the agent's steps arrive, reads the scorecard and failures, toggles fixes on the demo store, reruns, and compares before and after. Runs take 10 to 40 seconds. PayPal can pause a run as "awaiting human approval", which needs clear instructions. The demo store itself is deliberately plain and is not part of the dashboard's look.

## Capabilities and Constraints

- Data comes from the existing FastAPI API: `/api/runs`, `/api/runs/{id}`, `/api/runs/compare`, `/api/runs/{id}/explain`, `/api/market/{sku}`, `/api/health`, `/store/admin/flaws.json`.
- React + Vite + TypeScript. Tables use AG Grid Community only (no Enterprise features).
- The Simple view works on phones (375px and up). The Advanced view is desktop only (1024px and up).
- Mock or fixture data (mock LLM, mock PayPal, scripted navigator, recorded Channel3 fixtures) must always carry a visible label.
- Scope lock: one store, one product flow, one score. No accounts.
- The scoring rubric (rules `2026-11-05.3`) is frozen after Day 5; the numbers in the video script depend on it.

## Brand Commitments

- Name: GhostShopper. Tagline: "See your store through an AI shopper's eyes."
- "Ledger": white, square, hairline rules, soft ink, Geist and Geist Mono, colour only for status, with a framed G mark. See docs/UI_SPEC.md.
- PayPal appears only as the payment integration. Never imitate PayPal's branding or imply GhostShopper is a PayPal product.

## Evidence on Hand

- Real run data in SQLite: scores, checks with screenshots and selectors, steps, orders with fees, before/after comparisons (e.g. 49 to 100).
- Detection benchmark results in docs/METRICS.md (closed-loop; must not be presented as general accuracy).
- No customers, testimonials or live-merchant results exist. Don't invent any.

## Product Principles

1. Evidence over assertion: every failure shows what the browser saw.
2. Fair to the merchant: separate what the store controls from what it doesn't.
3. Show the fix, then prove it: before/after is the centre of the story.
4. Honest labels: anything mocked says so on screen.
