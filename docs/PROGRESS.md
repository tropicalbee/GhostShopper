# Progress

Entries before 2026-11-11 are in [archive/PROGRESS-2026-11-05-to-11-10.md](archive/PROGRESS-2026-11-05-to-11-10.md). The full original file, before the split: [PROGRESS.md at a44951e](https://github.com/tropicalbee/GhostShopper/blob/a44951e642b2f8d88d750b7c7eaa2519ad2afeab/docs/PROGRESS.md).

## 2026-11-12, session 11 (final audit fixes)

### Done
- README intro shortened to two sentences.
- Code fixes from the audit (applied by another agent): catalog time bound and daily cap, 5 `look_at_page` calls per run, popup screenshot key, id validation on order read and verify (both now agent-only behind an internal key), vault buyer from the environment for hosted real runs, banner without run numbers, architecture and data-model diagrams and the mermaid blocks updated, docs/REPRODUCE.md, 400 `RUN_CONFIG` with no LLM, localhost origins hidden in every failure column, one-time log for short `X-Forwarded-For`.
- Docs: PRD flaw table now has all 20 flaws; SCHEMA has the missing `runs` columns; VIDEO_SCRIPT matches cut v2; README model attribution follows the local database; test count, Impact bullets, Kernel and hosted-purchase lines state the evidence; TRD, APPFLOW, CHANGELOG, PLAN and DECISIONS updated.
- Hosted run 5 (Kernel, sandbox, popup): 41/75, blocked at step_limit, popup approval timed out at the password step after 120 s, no capture. Numbers in METRICS.md.
- Frontend files with no importers, left in place (the build leaves them out, so the shipped app is unaffected): `frontend/src/components/MoneyFlow.tsx`, `MoneyHero.tsx`, `Nav.tsx`, `Walkthrough.tsx`, `ShopperFlow.tsx`, `frontend/src/screens/Home.tsx`, `frontend/src/components/ui/{badge,card,separator,sonner,tooltip}.tsx`, `frontend/src/assets/walkthrough/`.

### Not verified
- Full suite: 646 of 657 passed; the 11 failures were test setups (no LLM configured, old health keys), fixed and rerun green (59 passed). The whole suite was not rerun after that fix.
- Hosted vault purchase done after the redeploy: hosted run 3, Kernel, $24.00 captured, store order #1048 Paid, 4 of 4 links ok (METRICS.md). Local run 61 proved the same path first.
- The live-site latency figures came from the hosted check.

### Next
1. Redeploy with the vault env vars.
2. One hosted vault run.
3. Fresh clone test.
4. Video link into the README and Devpost.
5. Submit by 12:00 PT (01:30 IST).

### Blockers
- None. The GitHub repo returned 404 during the audit and was made public the same evening (repo page and LICENSE return 200).

## 2026-11-12, session 10 (final audit)

### Done
- Read-only crawl of the hosted site at 1440 and 390 px (landing, new check, my checks, ledger, run 1 and 2, compare, advanced, store, health, catalog): no horizontal overflow, no console errors beyond expected 404s (no earlier check to compare for run 1, no other-path check).
- Example checks leaked `http://localhost:8000` in the Advanced grid ("What we saw"); the grid now shows the store path only.
- `.env.example` and README now list `ALLOW_PRIVATE_URLS`.
- Channel3 text updated: the hosted `/api/market/FH-MUG-01` returns live Channel3 results (18 similar, median $20.13). Numbers in METRICS.md.
- README and DEVPOST links all resolve; setup scripts, Dockerfile and gitignore reviewed, nothing required at runtime is ignored.

### Not verified
- Fresh clone run, hosted redeploy of the grid fix, the frontend change in a browser (build passes only).

### Next
- Redeploy on Render, submit before 12:00 PT.

### Blockers
- None.

## 2026-11-12, session 9 (WebMCP, catalog readiness)

### Done
- New framing: structured tools fix the browsing half only, so GhostShopper runs the same purchase through the storefront and through WebMCP tools and checks both against the same five-record trace.
- WebMCP path built on Chromium's native WebMCP over CDP, with a shim fallback. Fernhill gets an adapter for the `shopping.*` contract PayPal's showcase registers. PayPal's showcase is used as a labelled external demo.
- Live runs on Nemotron 3.5 Super VL 120B: 53 (headless approval stuck), 54 (Fernhill WebMCP, capture COMPLETED $24.00, store order still Awaiting payment), 56 (PayPal showcase, $25.00 gift card), 57 (browser agent on the same store, 65/100). Compare 57 vs 54 gives the same first mismatch on both paths.
- Native discovery on PayPal's showcase (4 tools) and on the Shopify demo store (12 tools).
- Catalog readiness (demo store 12/12 and 0/12; Shopify demo 0 of 2 checked, third page 429).
- Shopper vision (optional `look_at_page`), live-verified: run 59 (price only in an image) read $24.00 from the screenshot and bought, order #1078 Paid, score unchanged at 65/100. Run 58 (JSON-LD still had the price) never called it.
- Mobile landing fixes, link preview card, demo-store paths, trace matrix timeout fix.
- README, DEVPOST, PRD, TRD, SCHEMA, APPFLOW, DECISIONS, METRICS, PLAN, CHANGELOG, issues-and-fixes and `research/paypal-webmcp.md` updated.

### Next
1. Push, Render redeploy with `VISION_MODEL`, hosted check.
2. Update the demo video.
3. Fresh-clone test, submit before 12:00 PT.

### Blockers
- None.


## 2026-11-12, session 8 (video v2)

### Done
- New video story: "Paid, but your store doesn't know." Three live Sandbox runs on the vault payment: 50 (PayPal captured $24.00, store order #1071 still Awaiting payment, 65/100), 51 (fixed, 100/100, #1072 Paid), 52 (hidden instructions for agents flagged, not followed).
- `record_demo.py --bad-flaws` picks the bad store's flaws; the admin scene unticks exactly those and fails if any flaw stays on. New `record_tour.py` (read-only site tour) and `record_safety.py` (one live run with hidden instructions, flaws restored after).
- Script for cut v2 in VIDEO_SCRIPT.md, checked against the code and the runs. No mock numbers, no model named in the voice.
- Edit rebuilt as `video/src/V2.tsx` (Remotion): shots anchored to voice lines, zooms on recorded focus boxes, no captions, a five-stage tracker in the trace's real order, end card. Voice: Kokoro "Heart" from Hugging Face, local ONNX. Music: an original pad.

### Next
1. Watch `video/out/ghostshopper-v2.mp4`, then upload to YouTube as Public before 11:30 PM IST.
2. Paste the link into the README `<!-- VIDEO_URL -->` marker and Devpost.
3. Optional: Shibangi records the same script in their own voice and it replaces `voice-fit.wav`.

### Blockers
- None.


## 2026-11-12, session 7 (demo video)

### Done
- Video pipeline moved to Remotion in `video/`: dashboard-style title, score and end cards, screen footage in a rounded frame with zooms on the key spots, kinetic captions, music ducked under the voice. `scripts/video/record_demo.py` now records a CDP screencast at 1.5x density (Playwright's own video was too soft to zoom into) and saves zoom targets in `markers.json`.
- Live take recorded: run 47 (bad store, 18/100, the agent gave up after 25 steps) and run 48 (fixed store, 100/100, bought in 11 steps with the vault payment, $24.00 captured, $22.67 net, 4 of 4 IDs linked). Both on Nemotron 3.5 Lightning with real Sandbox calls.
- VIDEO_SCRIPT.md rewritten for the 18 to 100 story, vault payment and the Mako voice.
- PayPal popup fix: an unknown form now gets 12 s to show a known button before the run asks for a human, and the popup is saved as evidence.
- `POST /api/runs` accepts `payment: "vault"` as a dev option. The sandbox buyer's vault token is saved.
- Tests: 76 PayPal/checkout and 79 run/vault/API tests passed.

### Next
1. User: 11 Mako clips into `demo-video/live/voice/row01..row11.wav`, one music track into `demo-video/live/music.mp3`.
2. `cd video && npm run studio` to check, then `npm run render`.
3. YouTube upload (Public), link into the README `<!-- VIDEO_URL -->` marker and Devpost, submit before 12:00 PT.

### Blockers
- None. NVIDIA's 120B Nemotron was slow (about 40 s per reply) and briefly down (503) today, so the video take used Lightning.

## 2026-11-12, session 6 (deploy, open sandbox, audit, video prep)

### Done
- Render deploy is live at https://ghostshopper.onrender.com. Health shows PayPal sandbox configured and the LLM configured, with `EXAMPLE_RUNS=1`.
- Real PayPal Sandbox purchases are open to every visitor under the daily caps, and New check picks the real sandbox by default. The presenter token now only unlocks the flaw toggles and the Kernel live view.
- One LLM config for every provider (`LLM_PROVIDER`, `LLM_MODEL`, `LLM_API_KEY`). The Groq-only code and variables are gone.
- LLM timeouts are retried, which fixed hosted run 1 (`ReadTimeout` after 469 s).
- Real runs 31 (bad store, 49) and 34 (fixed store, 100) ship in `backend/app/examples/` and load as shared examples on every start, so judges see them after a restart. The bundle is redacted.
- Security audit (quick profile, source only), report at `C:/Users/shiba/security-audit-skill/GhostShopper/run-1/REPORT.md`: no confirmed findings, 8 leads that need validation, 6 of them fixed in code. The git history holds no secrets.
- Docs follow the outside review: the 49 to 100 story instead of a lost sale, mock and live numbers labelled, trace wording, PayPal positioning (not Agent Ready or WebMCP), hosted URL, new banner wording, footer GitHub link, LICENSE names tropicalbee, GitHub About filled in.
- New `docs/VIDEO_SCRIPT.md`: a 2:35 YC-style demo with an AI voiceover, no face and no third-party brands.
- Full suite: 540 passed.

### In progress
- Superseded by the Remotion cut (see DECISIONS.md, "2026-11-12: demo video"). Video pipeline: `scripts/video/record_demo.py` (Playwright records the dashboard) and `scripts/video/build_video.py` (ffmpeg cuts, speeds up, adds cards and voice), output in `demo-video/` (gitignored). A Sonnet agent was building it and dry-running it on mock data when the session ended; check whether both files exist and work.

### Next
1. Video in a new session: check the dry run, record the two live runs locally, add the voice clips (row01 to row11 from Google AI Studio, Windows Zira as backup), the user renders, upload to YouTube as Public.
2. Paste the YouTube link into the README `<!-- VIDEO_URL -->` marker and the Devpost form.
3. Optional: one real-sandbox check on the hosted URL, which is the missing Kernel purchase proof.
4. Submit before Nov 12, 12:00 PT (1:30 AM IST).

### Blockers
- None. The deadline is today.

## 2026-11-11, session 5 (pitch, diagram, README, click-through)

### Done
- Final pitch applied to the README, PRD and video script, plus a new Devpost description in `docs/DEVPOST.md`.
- Detailed architecture diagram redrawn: one number per step, no crossing lines, A and B for the market check and fix wording. Step 10 now points at the browser tools, and the Runs API box names `main.py, /api/market`, both to match the code.
- README rewritten: banner with the PayPal pitch, today's live runs only, three cropped screenshots from runs 30 and 34 in `docs/screenshots/2026-11-11/`, simple architecture diagram, results split into live and mock, setup per OS, credits.
- Market filter (duplicates and multi-packs out of the median) finished, 24 market tests pass.
- Click-through smoke test of the store and every dashboard page in mock mode: no bugs, 523 tests passed, frontend build ok.

### Not verified
- Nothing live this session. The README's numbers come from METRICS.md (runs 31 to 37).

### Next
1. Render deploy: New, Blueprint, `tropicalbee/GhostShopper`, fill secrets (`LLM_MODEL`, `LLM_API_KEY`, PayPal, sandbox buyer, `KERNEL_API_KEY`, `DEMO_ADMIN_TOKEN`), then set `APP_BASE_URL` and Manual Deploy.
2. Ping `<url>/api/health` every 10 min from cron-job.org so the free tier never sleeps.
3. After the final deploy, run 2 checks on the hosted URL (bad store, then fixed, mock PayPal) so the dashboard isn't empty. The SQLite disk starts empty on every deploy (seen in the local Docker test: `/api/runs` returned `[]`).
4. Hosted URL and video link into the README markers (`<!-- HOSTED_URL -->`, `<!-- VIDEO_URL -->`), fresh-clone test, video, Devpost.
5. Optional MCP branch only if time allows. Cutoff Nov 12, 08:00 PT (9:30 PM IST).

Deadline: Nov 12, 12:00 PT = Nov 13, 1:30 AM IST. Aim to submit by Nov 12, 10:00 PM IST.

### Blockers
- The Render dashboard keeps loading on the user's network (Render status is operational). Try incognito, another browser, `ipconfig /flushdns` or a phone hotspot.
- Local Docker image builds and runs fine (health ok, dashboard and store load).

## 2026-11-11, session 4 (live runs, ID links, Kernel fix, new logo)

### Done
- Live runs with real Nemotron and the real PayPal sandbox: bad store 49/100 and purchased (run 31), fixed store 100/100 (run 32), cassettes recorded. Run 34 after the ID-link change: 100/100, all four ID links ok on real sandbox data.
- Shopify demo store, browse only: 62/100 on 84 of 100 points, same 5 issues locally (run 33) and in Kernel (run 37).
- Trace: four ID link checks, `records_not_linked`, broken links first. A paid order with no PayPal id makes the PayPal stages unknown and raises `paid_without_paypal_reference`. Trace benchmark now 33/33.
- Store order is created before the PayPal order, its number goes to PayPal as `custom_id`, and the capture id is saved on it.
- Kernel fix: service workers blocked locally and bypassed in Kernel, request guard never raises, run limit 600 s, session always deleted.
- `LLM_PROVIDER=nvidia`, accurate "not tested" reasons, tests never use Kernel or paid keys from `.env`.
- Ledger shows matched for sandbox runs 18, 31, 32 and 34 after enabling Transaction search.
- Frontend: "Linked by ID" section, ghost with a shopping bag as logo and favicon, header buttons hide when the page shows the same ones, the ghost walks the landing page stepper to the first mismatch.
- Full suite 488 passed. Numbers in METRICS.md.

### Not verified
- The Linked by ID section has not been seen on screen with real data.
- A Kernel purchase on the hosted URL.
- The `test_trace_matrix` subset test failed twice under load, then passed in later full runs. Cause unknown.

### Next
1. Render deploy with Kernel as the hosted browser (`BROWSER_PROVIDER=kernel` on Render), a sandbox purchase on the hosted URL, hosted URL in the README.
2. README limitation wording: the full five stage trace works on the demo store only, real stores don't expose their order records yet. Carry it into Devpost and the video script. Humanizer pass.
3. Fresh-clone test.
4. Devpost text and video.
5. Optional: Channel3 key.

### Blockers
- None. Kernel credit left: 4.95 of 5.00 USD.
