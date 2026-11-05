import type { ReactNode } from "react";

import { checkedAt, ModeLabels, platformName, storeName } from "@/components/bits";
import type { Health, Run } from "@/lib/api";
import { cn } from "@/lib/utils";

const OUTCOME: Record<string, (run: Run) => string> = {
  purchased: (r) => `Bought the ${r.target_product}`,
  reached_checkout: () => "Reached checkout",
  blocked: () => "The payment didn't go through",
  gave_up: () => "Stopped before paying",
  error: () => "The check didn't finish",
};

export function ViewSwitch({ runId, advanced }: { runId: number; advanced: boolean }) {
  const item = (on: boolean) =>
    cn("flex h-8 items-center px-3 text-sm font-medium no-underline transition-colors", on ? "bg-panel text-foreground shadow-[inset_0_0_0_1px_var(--border)]" : "text-muted-foreground hover:text-foreground");
  return (
    <nav aria-label="View" className="inline-flex gap-0.5 border border-line p-0.5">
      <a href={`#/run/${runId}`} aria-current={!advanced ? "page" : undefined} className={item(!advanced)}>
        Simple
      </a>
      <a href={`#/run/${runId}/advanced`} aria-current={advanced ? "page" : undefined} className={item(advanced)}>
        Advanced
      </a>
    </nav>
  );
}

export function RunHead({ run, health, actions, actionsClassName }: { run: Run; health: Health; actions?: ReactNode; actionsClassName?: string }) {
  const platform = platformName(run.platform);
  const meta = [
    run.live ? "Live store, checked up to the PayPal button" : "Demo store",
    platform && `Runs on ${platform}`,
    `Checked ${checkedAt(run.started_at)}`,
    `${run.steps.length} steps`,
    run.outcome && OUTCOME[run.outcome]?.(run),
  ].filter(Boolean) as string[];
  return (
    <header className="pt-8">
      <p className="flex gap-2 text-[13px] text-muted-foreground">
        <a href="#/checks" className="text-muted-foreground no-underline hover:text-foreground">
          My checks
        </a>
        <span aria-hidden>/</span>
        <span className="text-foreground">Check {run.id}</span>
      </p>
      <div className="flex flex-col gap-5 border-b-[1.5px] border-rule pt-2 pb-5 xl:flex-row xl:items-end xl:justify-between">
        <div className="min-w-0">
          <h1 className="text-[1.875rem] leading-tight font-semibold tracking-[-0.03em] [overflow-wrap:anywhere]">{storeName(run)}</h1>
          <ul className="mt-2 flex flex-wrap gap-x-5 gap-y-1 text-[13px] text-muted-foreground">
            {meta.map((m) => (
              <li key={m}>{m}</li>
            ))}
          </ul>
        </div>
        {actions && <div className={cn("flex shrink-0 flex-wrap items-center gap-3", actionsClassName)}>{actions}</div>}
      </div>
      <div className="mt-4">
        <ModeLabels run={run} health={health} />
      </div>
    </header>
  );
}
