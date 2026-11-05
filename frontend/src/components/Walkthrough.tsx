import { ChevronLeft, ChevronRight, CircleAlert, CircleCheck, Pause, Play } from "lucide-react";
import { useEffect, useState } from "react";

import { PathStrip, STAGES, type PathStage } from "@/components/bits";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";
import { useFetch } from "@/lib/hooks";
import { cn } from "@/lib/utils";

// What happens at each stage, in plain words. The points come from the scoring rules (GET /api/rubric);
// the demo lines describe what the shopper really meets on the Fernhill Ceramics demo store with its flaws on.
const STORY: Record<string, { does: string; checks: string[]; demo: string; ok: boolean }> = {
  discover: {
    does: "Opens your home page and looks for the product by its name, like a shopper who knows what they want.",
    checks: ["The product is linked from your home page by its name"],
    demo: "Found the Speckled Stoneware Mug from the home page.",
    ok: true,
  },
  details: {
    does: "Reads the product page: the name, the price and its currency, whether it's in stock, and the photos.",
    checks: ["The price is written as text", "The page carries the product details AI shoppers read first", "Stock is shown", "The price says its currency", "Photos are described"],
    demo: "The price is drawn inside a picture, so the shopper couldn't read it.",
    ok: false,
  },
  checkout: {
    does: "Picks the button that buys and goes to checkout.",
    checks: ["One clear Buy now or Add to cart button", "No extra form before paying", "The price at checkout matches the product page", "Sold-out items can't be bought"],
    demo: "The buttons say Continue, Proceed and Go, so it clicked the wrong one first.",
    ok: false,
  },
  payment: {
    does: "Finds your PayPal button. On our demo store it also pays in the PayPal sandbox. On your store it stops there.",
    checks: ["The PayPal button is there and can be clicked", "The payment is approved and captured (demo store only)", "The amount and PayPal's fee add up"],
    demo: "Paid 24.00 USD. PayPal's fee was 1.33 USD.",
    ok: true,
  },
  outcome: {
    does: "Decides whether the whole trip worked, from your home page to a finished order.",
    checks: ["The shopper finished without getting stuck"],
    demo: "Bought the mug, after a few wrong turns.",
    ok: true,
  },
};

const STEP_MS = 3500;

export function Walkthrough() {
  const rubric = useFetch(api.rubric, []);
  const [active, setActive] = useState(0);
  const [playing, setPlaying] = useState(false);
  const keys: string[] = STAGES.map(([k]) => k);

  useEffect(() => {
    if (!playing) return;
    if (active >= keys.length - 1) {
      setPlaying(false);
      return;
    }
    const t = window.setTimeout(() => setActive((i) => i + 1), STEP_MS);
    return () => window.clearTimeout(t);
  }, [playing, active, keys.length]);

  if (!rubric.data) return <div className="hatch h-40 border" aria-busy="true" aria-label="Loading how a check works" />;

  const points = Object.fromEntries(rubric.data.stages.map((s) => [s.key, s.points]));
  // The strip fills up to the selected stage, the way the shopper moves through the store.
  const stages: PathStage[] = STAGES.map(([key, name], i) => ({ key, name, points: points[key] ?? 0, fill: i <= active ? 1 : 0, state: "idle" }));
  const key = keys[active];
  const story = STORY[key];
  const play = () => {
    if (active >= keys.length - 1) setActive(0);
    setPlaying(true);
  };

  return (
    <div>
      <PathStrip
        stages={stages}
        active={key}
        onSelect={(k) => {
          setPlaying(false);
          setActive(keys.indexOf(k));
        }}
        label="The five stages of a check. Choose one to see what happens there."
      />

      <div aria-live="polite" className="mt-6 grid gap-6 border-t pt-6 md:grid-cols-3 md:gap-8">
        <div>
          <h3 className="flex items-baseline gap-3 text-lg font-semibold tracking-[-0.01em]">
            {stages[active].name}
            <span className="num text-[13px] font-normal text-muted-foreground">{stages[active].points} of 100 points</span>
          </h3>
          <p className="mt-2 text-muted-foreground">{story.does}</p>
        </div>
        <div>
          <p className="text-[13px] font-medium text-muted-foreground">What we check</p>
          <ul className="mt-2 space-y-1.5">
            {story.checks.map((c) => (
              <li key={c} className="flex gap-2">
                <span className="mt-[0.6em] size-1 shrink-0 bg-foreground/50" aria-hidden />
                {c}
              </li>
            ))}
          </ul>
        </div>
        <div>
          <p className="text-[13px] font-medium text-muted-foreground">On our demo store</p>
          <p className={cn("mt-2 flex gap-2", !story.ok && "text-bad")}>
            {story.ok ? (
              <CircleCheck className="mt-0.5 size-4 shrink-0 text-good" aria-label="Passed" />
            ) : (
              <CircleAlert className="mt-0.5 size-4 shrink-0" aria-label="Problem" />
            )}
            {story.demo}
          </p>
        </div>
      </div>

      <div className="mt-6 flex flex-wrap items-center gap-2">
        <Button variant="outline" className="h-10 border-line" onClick={() => (playing ? setPlaying(false) : play())}>
          {playing ? <Pause aria-hidden /> : <Play aria-hidden />}
          {playing ? "Pause" : "Play the walkthrough"}
        </Button>
        <Button variant="ghost" size="icon" className="size-10" aria-label="Previous stage" disabled={active === 0} onClick={() => { setPlaying(false); setActive((i) => i - 1); }}>
          <ChevronLeft aria-hidden />
        </Button>
        <Button variant="ghost" size="icon" className="size-10" aria-label="Next stage" disabled={active === keys.length - 1} onClick={() => { setPlaying(false); setActive((i) => i + 1); }}>
          <ChevronRight aria-hidden />
        </Button>
        <span className="num ml-1 text-[13px] text-muted-foreground">
          {active + 1}/{keys.length}
        </span>
      </div>
    </div>
  );
}
