---
version: 1
slug: "frontend-src"
primary_target: "frontend/src"
related_targets: []
---

Scope: the GhostShopper merchant dashboard (frontend/src). Visitor mode: Operate.

Audience: small shopkeepers with little tech knowledge, often on phones (primary); judges and developers on desktop (secondary). Job: paste a store link, watch the shopper, read one score and the top three fixes, send the technical report on, check again, see before and after. Constraints: shadcn components, AG Grid Community for the failures table only, Recharts for charts, light only, mock data always labelled.

Chosen direction: A, "Ledger", user-pinned on 2026-11-06 after two static mocks (scratchpad mocks a-adv.png and a-simple.png, after impeccable's quieter pass). The user's references: ui.shadcn.com and their Razorpay Buildathon dashboard. Memorable moment: the shopper's path.

## Direction contract

THESIS: a calm working ledger, not a dribbble dashboard; the shopper's path is the one object a merchant remembers. It refuses the category default of a greeting over four stat cards, a gauge, and pastel charts.

OWN-WORLD: white ground, hairline cool-grey rules (#e7e7ea), square corners, soft ink #18181b, a 1.5px #3f3f46 rule closing page and table heads, pale panel #f7f7f8, Geist for text and Geist Mono only for data, colour only for status (red #b42318 store-caused, green #18794e good, amber #93600a warn), one dark primary button per screen, a framed G mark.

STORY: the merchant understands that an AI shopper tried to buy from them, sees exactly where it got stuck and why it costs sales, believes the score because it comes from checks, fixes the top three things, and checks again to watch the score rise.

FIRST VIEWPORT: Home at 1440 x 900. Left sidebar (mark, New check, My checks, recent checks). Main column: the question as a 52px heading, one sentence, the link box with the attached Check my store button (the only dark fill), the demo link and the safety line; below, under a 1.5px rule, four numbered questions the shopper asks in the order it shops. The user rejected an interactive path walkthrough on Home on 2026-11-06, so the path lives on Live, Results and Advanced, not on Home.

FORM: Ledger, the user's own pick (position 1 of the two shown). Signature interaction: the shopper's path, filling stage by stage on Live as checks come in, compact on Results, proportional with the stuck reasons on Advanced.
seed: none (user-pinned, no roll)
No concept roll ran for this direction: the user pinned it from two mocks built from their own references. This is a skipped roll, disclosed to the user, not an unavailable one. An earlier session's roll (reroll1.txt) belongs to directions the user rejected and does not apply.

FINISH: unreviewed and undocumented is unfinished; this build ends with the finish review, the verdict, DESIGN.md, and every shipping raster carrying its provenance

Unresolved: none.
