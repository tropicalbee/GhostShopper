import type { LucideIcon } from "lucide-react";
import { CircleAlert, CircleCheck, CircleHelp, Info } from "lucide-react";
import type { ReactNode } from "react";
import { Cell, Pie, PieChart } from "recharts";

import { Badge } from "@/components/ui/badge";
import type { Health, Run, Scorecard } from "@/lib/api";
import { cn } from "@/lib/utils";

// Small uppercase card title with an icon, as in the reference dashboard.
export function Label({ icon: Icon, children, className }: { icon: LucideIcon; children: ReactNode; className?: string }) {
  return (
    <div className={cn("flex items-center gap-2 text-xs font-medium tracking-wide text-muted-foreground uppercase", className)}>
      <Icon className="size-4" aria-hidden />
      {children}
    </div>
  );
}

export function Panel({ className, children }: { className?: string; children?: ReactNode }) {
  return <section className={cn("rounded-xl border bg-card p-5", className)}>{children}</section>;
}

const STATUS: Record<Scorecard["simple"]["status"], { icon: LucideIcon; cls: string }> = {
  good: { icon: CircleCheck, cls: "bg-good/10 text-good" },
  warn: { icon: CircleAlert, cls: "bg-warn/15 text-[oklch(0.5_0.12_60)]" },
  bad: { icon: CircleAlert, cls: "bg-bad/10 text-bad" },
  unknown: { icon: CircleHelp, cls: "bg-muted text-muted-foreground" },
};

// Colour never stands alone: the pill always carries an icon and words.
export function StatusPill({ level, text, className }: { level: Scorecard["simple"]["status"]; text: string; className?: string }) {
  const { icon: Icon, cls } = STATUS[level];
  return (
    <span className={cn("inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-sm font-medium", cls, className)}>
      <Icon className="size-4" aria-hidden />
      {text}
    </span>
  );
}

// Visible labels for anything that isn't the real thing (spec rule: mock data always says so).
export function ModeLabels({ run, health }: { run: Run; health?: Health | null }) {
  const labels: string[] = [];
  if (run.example) labels.push("Example check (shared demo, not yours)");
  if (run.llm === "scripted") labels.push("Practice run (scripted shopper, not AI)");
  if (run.llm === "mock") labels.push("Practice run (replayed shopper, not live AI)");
  if (run.checkout && run.paypal_mode === "mock") labels.push("Mock PayPal");
  if (!labels.length && health?.paypal_mode === "mock" && !run.live) labels.push("Mock PayPal");
  if (!labels.length) return null;
  return (
    <div className="flex flex-wrap gap-2">
      {labels.map((l) => (
        <Badge key={l} variant="outline" className="h-6 gap-1 bg-card px-2.5 text-muted-foreground">
          <Info aria-hidden />
          {l}
        </Badge>
      ))}
    </div>
  );
}

const SEGMENTS = 24;

// Segmented half-ring: dark segments for points earned, light ones for the rest.
export function ScoreGauge({ score, size = 260, caption }: { score: number; size?: number; caption?: ReactNode }) {
  const filled = Math.round((score / 100) * SEGMENTS);
  const data = Array.from({ length: SEGMENTS }, () => ({ v: 1 }));
  const height = size / 2 + 12;
  return (
    <div className="flex flex-col items-center gap-2">
    <div className="relative" style={{ width: size, height }} role="img" aria-label={`Score ${score} out of 100`}>
      <PieChart width={size} height={height} margin={{ top: 0, right: 0, bottom: 0, left: 0 }}>
        <Pie
          data={data}
          dataKey="v"
          cx="50%"
          cy={size / 2}
          startAngle={180}
          endAngle={0}
          innerRadius={size * 0.32}
          outerRadius={size / 2 - 2}
          paddingAngle={2.5}
          cornerRadius={4}
          stroke="none"
          isAnimationActive={false}
        >
          {data.map((_, i) => (
            <Cell key={i} fill={i < filled ? "var(--foreground)" : "var(--border)"} />
          ))}
        </Pie>
      </PieChart>
      <span className="absolute inset-x-0 bottom-0 text-center text-5xl leading-none font-semibold tracking-tight tabular-nums">
        {score}
      </span>
    </div>
    {caption && <span className="text-sm text-muted-foreground">{caption}</span>}
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
