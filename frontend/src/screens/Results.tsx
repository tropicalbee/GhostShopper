import { ArrowRight, Info, RotateCw, Settings2, Store } from "lucide-react";
import { useState } from "react";

import { hostOf, ModeLabels, Panel, platformName, ScoreGauge, StatusPill } from "@/components/bits";
import { DeveloperDialog, ShowMeDialog } from "@/components/dialogs";
import { Button } from "@/components/ui/button";
import { sameSeries, startCheck, type Health, type PlainFix, type Run, type RunSummary } from "@/lib/api";
import { go, useCountUp } from "@/lib/hooks";

function FixCard({ fix, n }: { fix: PlainFix; n: number }) {
  return (
    <Panel className="flex flex-col gap-3">
      <div className="flex items-start gap-3">
        <span className="flex size-7 shrink-0 items-center justify-center rounded-full bg-foreground text-sm font-semibold text-background">
          {n}
        </span>
        <div>
          <h3 className="text-lg leading-snug font-semibold">{fix.title}</h3>
          <p className="mt-1 text-muted-foreground">{fix.why}</p>
        </div>
      </div>
      <div className="rounded-lg bg-muted/60 p-4 sm:ml-10">
        <p className="text-sm font-medium">How to fix it</p>
        <p className="mt-1">{fix.steps ?? fix.how}</p>
      </div>
      {fix.screenshot_url && (
        <div className="sm:ml-10">
          <ShowMeDialog src={fix.screenshot_url} title={fix.title} />
        </div>
      )}
    </Panel>
  );
}

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

  const earlier = runs.find((r) => r.id < run.id && sameSeries(run, r) && r.score != null);
  // Visitors can't change the shared demo store, so its before and after comes from the shared example pair.
  const scored = (r: RunSummary) => r.example && !r.live && r.score != null;
  const example = !run.live && !earlier && !health.demo_admin_open
    ? runs.find((r) => scored(r) && runs.some((p) => scored(p) && p.id < r.id))
    : undefined;
  const platform = platformName(card?.platform);

  return (
    <div className="mx-auto flex max-w-2xl flex-col gap-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="flex items-center gap-2 text-muted-foreground">
          <Store className="size-4" aria-hidden />
          {run.live ? hostOf(run.store_url) : "Demo store (Fernhill Ceramics)"}
        </p>
        {wide && card && (
          <Button variant="ghost" onClick={() => go(`/run/${run.id}/advanced`)}>
            <Settings2 aria-hidden />
            Advanced view
          </Button>
        )}
      </div>
      <ModeLabels run={run} health={health} />

      {card ? (
        <Panel className="flex flex-col items-center gap-4 py-8 text-center">
          <h1 className="text-lg font-medium text-balance">{card.simple.label}</h1>
          <ScoreGauge score={score} caption={`${card.simple.score}% ${card.simple.of_what}`} />
          <StatusPill level={card.simple.status} text={card.simple.status_text} />
          {platform && <p className="text-sm text-muted-foreground">Your store runs on {platform}.</p>}
          {run.live && (
            <p className="max-w-md text-sm text-muted-foreground">
              We checked up to your PayPal button and stopped. We never pay on real stores.
            </p>
          )}
        </Panel>
      ) : (
        <Panel className="py-8 text-center">
          <StatusPill level="unknown" text="We couldn't check your store this time" />
          <p className="mt-4 text-muted-foreground">Something went wrong on our side. Please try again.</p>
        </Panel>
      )}

      {card && card.not_store_fault.length > 0 && (
        <p className="flex items-start gap-2 rounded-lg border bg-card p-4 text-sm">
          <Info className="mt-0.5 size-4 shrink-0 text-muted-foreground" aria-hidden />
          <span>
            <span className="font-medium">Not your store's fault: </span>
            {card.not_store_fault[0].plain}
          </span>
        </p>
      )}

      {card && card.simple.top_fixes.length > 0 && (
        <>
          <h2 className="mt-3 text-xl font-semibold">What to fix first</h2>
          {card.simple.top_fixes.map((f, i) => (
            <FixCard key={f.check} fix={f} n={i + 1} />
          ))}
          {card.simple.more_fixes > 0 &&
            (wide ? (
              <button
                type="button"
                onClick={() => go(`/run/${run.id}/advanced`)}
                className="min-h-11 text-left text-sm font-medium underline underline-offset-4"
              >
                + {card.simple.more_fixes} more {card.simple.more_fixes === 1 ? "fix" : "fixes"}
              </button>
            ) : (
              <p className="text-sm text-muted-foreground">
                {card.simple.more_fixes} more {card.simple.more_fixes === 1 ? "fix is" : "fixes are"} in the report for your developer.
              </p>
            ))}
        </>
      )}
      {card && card.simple.top_fixes.length === 0 && card.possible > 0 && (
        <Panel className="text-center">
          <p className="text-lg font-medium">Nothing to fix. AI shoppers can buy from your store.</p>
        </Panel>
      )}

      {error && <p role="alert" className="text-sm text-bad">{error}</p>}
      <div className="mt-2 flex flex-col gap-3 sm:flex-row">
        <Button onClick={again} disabled={busy} className="h-12 text-base sm:flex-1">
          <RotateCw aria-hidden />
          {busy ? "Starting…" : "Check my store again"}
        </Button>
        {card && <DeveloperDialog runId={run.id} />}
      </div>

      <div className="flex flex-col gap-1 text-sm">
        {earlier && (
          <button type="button" onClick={() => go(`/run/${run.id}/compare`)} className="flex min-h-11 items-center gap-1 font-medium underline-offset-4 hover:underline">
            See before and after
            <ArrowRight className="size-4" aria-hidden />
          </button>
        )}
        {example && (
          <button type="button" onClick={() => go(`/run/${example.id}/compare`)} className="flex min-h-11 items-center gap-1 font-medium underline-offset-4 hover:underline">
            See an example before and after on the demo store
            <ArrowRight className="size-4" aria-hidden />
          </button>
        )}
        {!run.live && health.demo_admin_open && (
          <a href="/store/admin" target="_blank" rel="noreferrer" className="min-h-11 py-3 text-muted-foreground underline underline-offset-4">
            Fix the demo store (opens its settings)
          </a>
        )}
      </div>
    </div>
  );
}
