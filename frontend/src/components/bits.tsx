import { memo, useMemo, type ReactNode } from "react";

import { Skeleton } from "@/components/ui/skeleton";
import type { Health, Run, Scorecard } from "@/lib/api";
import { cn } from "@/lib/utils";

export function Logo({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 32 32" className={cn("size-7 shrink-0", className)} aria-hidden="true">
      <rect x="1" y="1" width="30" height="30" fill="var(--background)" stroke="var(--foreground)" strokeWidth="2" />
      <path d="M21 10.5H10.5v11H21v-5.5h-5" fill="none" stroke="var(--foreground)" strokeWidth="2.4" strokeLinecap="square" />
      <rect x="22.5" y="22.5" width="3.5" height="3.5" fill="var(--foreground)" />
    </svg>
  );
}

// A region title: small, muted, sentence case, with an optional figure on the right.
export function Label({ children, aside, className }: { children: ReactNode; aside?: ReactNode; className?: string }) {
  return (
    <h2 className={cn("flex items-baseline justify-between gap-4 text-[13px] font-medium text-muted-foreground", className)}>
      <span>{children}</span>
      {aside && <span className="font-normal">{aside}</span>}
    </h2>
  );
}

export function Panel({ className, children }: { className?: string; children?: ReactNode }) {
  return <section className={cn("border bg-card p-6", className)}>{children}</section>;
}

const STATUS_COLOUR: Record<Scorecard["simple"]["status"], string> = {
  good: "bg-good",
  warn: "bg-warn",
  bad: "bg-bad",
  unknown: "bg-line",
};

// Colour never stands alone: a small square plus the words.
export function StatusLine({ level, text, className }: { level: Scorecard["simple"]["status"]; text: string; className?: string }) {
  return (
    <p className={cn("flex items-start gap-2 font-medium", className)}>
      <span className={cn("mt-[0.55em] size-2 shrink-0", STATUS_COLOUR[level])} aria-hidden />
      {text}
    </p>
  );
}

export function Tag({ children }: { children: ReactNode }) {
  return <span className="inline-flex items-center border px-2.5 py-0.5 text-xs text-foreground/80">{children}</span>;
}

// Visible labels for anything that isn't the real thing (spec rule: mock data always says so).
export function ModeLabels({ run, health }: { run: Run; health?: Health | null }) {
  const labels: string[] = [];
  if (run.example) labels.push("Example check, shared demo");
  if (run.llm === "scripted") labels.push("Practice run, scripted shopper");
  if (run.llm === "mock") labels.push("Practice run, replayed shopper");
  if ((run.checkout && run.paypal_mode === "mock") || (!run.live && !run.checkout && health?.paypal_mode === "mock")) labels.push("Mock PayPal");
  if (!labels.length) return null;
  return (
    <div className="flex flex-wrap gap-2">
      {labels.map((l) => (
        <Tag key={l}>{l}</Tag>
      ))}
    </div>
  );
}

export function ScoreFigure({ score, className }: { score: number; className?: string }) {
  return (
    <p className={cn("num leading-[0.9] font-normal tracking-[-0.04em]", className)}>
      {score}
      <span className="ml-1 font-sans text-[0.25em] tracking-[-0.02em] text-muted-foreground">/100</span>
    </p>
  );
}

export const STAGES = [
  ["discover", "Find"],
  ["details", "Details"],
  ["checkout", "Checkout"],
  ["payment", "Payment"],
  ["outcome", "Finish"],
] as const;

export type PathStage = {
  key: string;
  name: string;
  points: number; // what the stage is worth: its width on the strip
  earned?: number; // shown as "9/40" when known
  fill: number; // 0 to 1 of the track drawn as earned
  stuck?: string | null; // the plain reason, under the stage, in red
  state?: "idle" | "reached" | "stuck";
};

export function stagesOf(card: Scorecard): PathStage[] {
  return STAGES.map(([key, name]) => {
    const earned = card.stages[key] ?? 0;
    const points = card.stage_possible?.[key] ?? earned;
    const firstFail = card.fixes.find((f) => f.stage === key && f.status === "failed");
    const stuck = firstFail ? (firstFail.plain?.title ?? firstFail.title) : null;
    return { key, name, points, earned, fill: points ? earned / points : 0, stuck, state: stuck ? "stuck" : "reached" } as PathStage;
  }).filter((s) => s.points > 0);
}

// The signature: the shopper's way to paying. Each stage is as wide as the points it's worth, grey for
// points earned, hatched for points lost, and the reason under the stage where it got stuck.
// With onSelect the stages are buttons (the Home walkthrough).
export function PathStrip({
  stages,
  compact = false,
  detail = true,
  active,
  onSelect,
  label = "Points by stage on the shopper's path",
}: {
  stages: PathStage[];
  compact?: boolean;
  detail?: boolean;
  active?: string;
  onSelect?: (key: string) => void;
  label?: string;
}) {
  return (
    <ol className={cn("flex", compact ? "gap-1" : "gap-1 sm:gap-1.5")} aria-label={label}>
      {stages.map((s) => {
        const body = (
          <>
            <div
              className={cn(
                "hatch relative border transition-[border-color] duration-200",
                compact ? "h-2" : "h-2.5",
                s.state === "stuck" ? "border-bad-soft" : active === s.key ? "border-foreground" : "border-border",
              )}
            >
              <div className="absolute inset-y-0 left-0 bg-earned transition-[width] duration-500 ease-out motion-reduce:transition-none" style={{ width: `${Math.round(s.fill * 100)}%` }} />
            </div>
            <p className={cn("mt-2 truncate font-medium", compact ? "text-xs" : "text-[13px] sm:text-sm", active && active !== s.key && "text-muted-foreground")}>
              {s.name}
            </p>
            {detail && !compact && (
              <>
                <p className="num text-xs text-muted-foreground sm:text-[13px]">{s.earned !== undefined ? `${s.earned}/${s.points}` : `${s.points} pts`}</p>
                {s.stuck && <p className="mt-1.5 hidden pr-2 text-[13px] text-bad sm:line-clamp-2">{s.stuck}</p>}
              </>
            )}
          </>
        );
        return (
          <li key={s.key} className={cn("min-w-0", compact ? "flex-1" : "min-w-12 sm:min-w-24")} style={compact ? undefined : { flexGrow: s.points, flexBasis: 0 }}>
            {onSelect ? (
              <button
                type="button"
                onClick={() => onSelect(s.key)}
                aria-pressed={active === s.key}
                className="block min-h-11 w-full text-left"
              >
                {body}
              </button>
            ) : (
              body
            )}
          </li>
        );
      })}
    </ol>
  );
}

// Memoized: Results re-renders on every frame of the score count-up, and the card does not change.
export const ShopperPath = memo(function ShopperPath({ card, compact = false }: { card: Scorecard; compact?: boolean }) {
  const stages = useMemo(() => stagesOf(card), [card]);
  return <PathStrip stages={stages} compact={compact} />;
});

// Placeholder for the stage strip while a run loads: same row of hatched tracks.
export function PathSkeleton({ compact = false }: { compact?: boolean }) {
  return (
    <div className="flex gap-1 sm:gap-1.5" aria-hidden>
      {[3, 2, 2, 2, 1].map((w, i) => (
        <div key={i} className="min-w-0" style={{ flexGrow: w, flexBasis: 0 }}>
          <div className={cn("hatch border", compact ? "h-2" : "h-2.5")} />
          <Skeleton className={cn("mt-2 h-3.5 w-3/4", compact && "h-3")} />
        </div>
      ))}
    </div>
  );
}

// The shape of a finished check while it loads: title rule, score panel on the left, fix list on the right.
export function RunSkeleton() {
  return (
    <div aria-busy="true" aria-label="Loading the check" role="status">
      <div className="border-b-[1.5px] border-rule pt-8 pb-5">
        <Skeleton className="h-4 w-40" />
        <Skeleton className="mt-3 h-8 w-72 max-w-full" />
      </div>
      <div className="mt-6 grid gap-8 lg:grid-cols-12 lg:gap-12">
        <div className="border bg-panel p-6 lg:col-span-5">
          <Skeleton className="h-4 w-32" />
          <Skeleton className="mt-4 h-20 w-44" />
          <Skeleton className="mt-5 h-5 w-56 max-w-full" />
          <div className="mt-6">
            <PathSkeleton compact />
          </div>
        </div>
        <div className="lg:col-span-7">
          <Skeleton className="h-6 w-48" />
          <div className="mt-3 border-t-[1.5px] border-rule">
            {[0, 1, 2].map((i) => (
              <div key={i} className="grid grid-cols-[2rem_minmax(0,1fr)] gap-x-3 border-b py-6">
                <Skeleton className="size-7" />
                <div>
                  <Skeleton className="h-5 w-2/3" />
                  <Skeleton className="mt-2 h-4 w-full" />
                  <div className="hatch mt-4 h-16 border" />
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

export function platformName(p: string | null | undefined): string | null {
  return ({ shopify: "Shopify", wix: "Wix", woocommerce: "WooCommerce" } as Record<string, string>)[p ?? ""] ?? null;
}

export function hostOf(url: string): string {
  try {
    return new URL(url).host;
  } catch {
    return url;
  }
}

export const storeName = (run: Pick<Run, "live" | "store_url">) => (run.live ? hostOf(run.store_url) : "Fernhill Ceramics");

export const checkedAt = (iso: string) =>
  new Date(iso).toLocaleString(undefined, { day: "numeric", month: "short", hour: "numeric", minute: "2-digit" });
