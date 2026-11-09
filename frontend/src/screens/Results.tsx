import { ArrowRight, Info, RotateCw } from "lucide-react";
import { memo, useMemo, useState } from "react";

import { platformName, ScoreFigure, ShopperPath, StatusLine } from "@/components/bits";
import { DeveloperDialog, ShowMeDialog } from "@/components/dialogs";
import { MoneyHero } from "@/components/MoneyHero";
import { PayPalReadiness } from "@/components/PayPalReadiness";
import { ProductFeedLine } from "@/components/ProductFeedLine";
import { RunHead, ViewSwitch } from "@/components/RunHead";
import { YourMoney } from "@/components/YourMoney";
import { Button } from "@/components/ui/button";
import { sameSeries, startCheck, type Health, type PlainFix, type Run, type RunSummary } from "@/lib/api";
import { go, useCountUp } from "@/lib/hooks";

// Results re-renders on each frame of the score count-up; the fix list does not change, so skip it.
const FixItem = memo(function FixItem({ fix, n }: { fix: PlainFix; n: number }) {
  return (
    <li className="grid grid-cols-[2rem_minmax(0,1fr)] gap-x-3 border-b py-6 last:border-b-0">
      <span className="num grid size-7 place-items-center border border-line text-[13px] text-foreground/80" aria-hidden>
        {n}
      </span>
      <div>
        <h3 className="text-[17px] leading-snug font-semibold tracking-[-0.01em]">{fix.title}</h3>
        <p className="mt-1 text-muted-foreground">{fix.why}</p>
        <div className="mt-4 border bg-panel px-4 py-3">
          <p className="text-[13px] font-semibold">How to fix it</p>
          <p className="mt-0.5">{fix.steps ?? fix.how}</p>
        </div>
        {fix.screenshot_url && (
          <div className="mt-2">
            <ShowMeDialog src={fix.screenshot_url} title={fix.title} />
          </div>
        )}
      </div>
    </li>
  );
});

export function Results({ run, health, runs, wide }: { run: Run; health: Health; runs: RunSummary[]; wide: boolean }) {
  const card = run.scorecard;
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const score = useCountUp(card?.simple.score ?? 0);

  const again = async () => {
    setBusy(true);
    setError(null);
    try {
      const { run_id } = await startCheck(run.live ? run.store_url : null);
      go(`/run/${run_id}`);
    } catch (e) {
      setError((e as Error).message);
      setBusy(false);
    }
  };

  // Scans the run list (up to 50 rows, with a nested scan for the example pair); cached across count-up frames.
  const { earlier, example } = useMemo(() => {
    const earlier = runs.find((r) => r.id < run.id && sameSeries(run, r) && r.score != null);
    // Visitors can't change the shared demo store, so its before and after comes from the shared example pair.
    const scored = (r: RunSummary) => r.example && !r.live && r.score != null;
    const example =
      !run.live && !earlier && !health.demo_admin_open
        ? runs.find((r) => scored(r) && runs.some((p) => scored(p) && p.id < r.id))
        : undefined;
    return { earlier, example };
  }, [run, runs, health.demo_admin_open]);
  const platform = platformName(card?.platform);
  const againLabel = busy ? "Starting…" : "Check my store again";

  return (
    <div>
      <RunHead
        run={run}
        health={health}
        actionsClassName="hidden sm:flex"
        actions={
          <>
            {wide && card && <ViewSwitch runId={run.id} advanced={false} />}
            {card && <DeveloperDialog runId={run.id} className="hidden sm:inline-flex" />}
            <Button onClick={again} disabled={busy} className="hidden h-10 sm:inline-flex">
              <RotateCw aria-hidden />
              {busy ? "Starting…" : "Check again"}
            </Button>
          </>
        }
      />
      {error && <p role="alert" className="mt-4 text-sm text-bad">{error}</p>}

      {card && <MoneyHero run={run} className="mt-6" />}
      {card && <PayPalReadiness run={run} className="mt-6" />}

      <div className="mt-8 grid grid-cols-1 gap-8 lg:grid-cols-12 lg:gap-12">
        <aside className="lg:col-span-5">
          {card ? (
            <section className="border bg-panel p-6 lg:sticky lg:top-20">
              <h2 className="text-[15px] text-muted-foreground">{card.simple.label}</h2>
              <ScoreFigure score={score} className="mt-4 text-[5.5rem]" />
              <StatusLine level={card.simple.status} text={card.simple.status_text} className="mt-5" />
              <div className="mt-6">
                <ShopperPath card={card} compact />
              </div>
              <p className="mt-4 text-[13px] text-muted-foreground">
                {card.simple.score}% {card.simple.of_what}
              </p>
              {(platform || run.live) && (
                <div className="mt-5 space-y-1 border-t pt-4 text-sm text-muted-foreground">
                  {platform && <p>Your store runs on {platform}.</p>}
                  {run.live && <p>We checked up to your PayPal button and stopped. We never pay on real stores.</p>}
                </div>
              )}
            </section>
          ) : (
            <section className="border bg-panel p-6">
              <StatusLine level="unknown" text="We couldn't check your store this time" />
              <p className="mt-2 text-muted-foreground">Something went wrong on our side. Please try again.</p>
            </section>
          )}
          {card && card.not_store_fault.length > 0 && (
            <p className="mt-4 flex items-start gap-2 border px-4 py-3 text-sm">
              <Info className="mt-0.5 size-4 shrink-0 text-muted-foreground" aria-hidden />
              <span>
                <span className="font-medium">Not your store's fault. </span>
                {card.not_store_fault[0].plain}
              </span>
            </p>
          )}
        </aside>

        <section className="lg:col-span-7" aria-labelledby="fix-first">
          {card && card.simple.top_fixes.length > 0 && (
            <>
              <h2 id="fix-first" className="border-b-[1.5px] border-rule pb-3 text-xl font-semibold tracking-[-0.02em]">
                What to fix first
              </h2>
              <ol>
                {card.simple.top_fixes.map((f, i) => (
                  <FixItem key={f.check} fix={f} n={i + 1} />
                ))}
              </ol>
              {card.simple.more_fixes > 0 && (
                <p className="border-t py-4 text-sm text-muted-foreground">
                  {wide ? (
                    <a href={`#/run/${run.id}/advanced`} className="font-medium text-foreground underline decoration-line underline-offset-4 hover:decoration-foreground">
                      {card.simple.more_fixes} more {card.simple.more_fixes === 1 ? "fix" : "fixes"} in the Advanced view
                    </a>
                  ) : (
                    <>
                      {card.simple.more_fixes} more {card.simple.more_fixes === 1 ? "fix is" : "fixes are"} in the report for your developer.
                    </>
                  )}
                </p>
              )}
            </>
          )}
          {card && card.simple.top_fixes.length === 0 && card.possible > 0 && (
            <div className="border-t-[1.5px] border-rule pt-5">
              <StatusLine level="good" text="Nothing to fix. AI shoppers can buy from your store." className="text-lg" />
            </div>
          )}

          {card && <YourMoney run={run} className="mt-8" />}
          {card && <ProductFeedLine run={run} className="mt-6" />}

          <div className="mt-6 flex flex-col gap-2.5 sm:hidden">
            <Button onClick={again} disabled={busy} className="h-12 text-base">
              <RotateCw aria-hidden />
              {againLabel}
            </Button>
            {card && <DeveloperDialog runId={run.id} className="h-12 text-base" />}
          </div>

          <div className="mt-6 flex flex-col items-start gap-1 text-sm">
            {earlier && (
              <button type="button" onClick={() => go(`/run/${run.id}/compare`)} className="inline-flex min-h-11 items-center gap-1.5 font-medium underline decoration-line underline-offset-4 hover:decoration-foreground">
                See before and after
                <ArrowRight className="size-4" aria-hidden />
              </button>
            )}
            {example && (
              <button type="button" onClick={() => go(`/run/${example.id}/compare`)} className="inline-flex min-h-11 items-center gap-1.5 font-medium underline decoration-line underline-offset-4 hover:decoration-foreground">
                See an example before and after on the demo store
                <ArrowRight className="size-4" aria-hidden />
              </button>
            )}
            {!run.live && health.demo_admin_open && (
              <a href="/store/admin" target="_blank" rel="noreferrer" className="inline-flex min-h-11 items-center text-muted-foreground">
                Fix the demo store (opens its settings)
              </a>
            )}
          </div>
        </section>
      </div>
    </div>
  );
}
