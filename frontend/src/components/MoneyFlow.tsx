import type { Run } from "@/lib/api";
import { money } from "@/lib/compare";
import { amountAtStake } from "@/components/ShopperFlow";
import { cn } from "@/lib/utils";

type Child = { label: string; value: string };

function Card({ label, value, tone, className }: { label: string; value?: string; tone?: "bad"; className?: string }) {
  return (
    <div className={cn("min-w-0 border-[1.5px] px-4 py-3", tone === "bad" ? "border-bad bg-bad/5" : "border-foreground/80", className)}>
      <p className="text-[11px] font-medium tracking-[0.12em] text-muted-foreground uppercase">{label}</p>
      {value && <p className={cn("num mt-1.5 text-xl", tone === "bad" && "text-bad")}>{value}</p>}
    </div>
  );
}

const CHILD_H = 76;
const GAP = 12;

// The PayPal settlement as a hub and its parts. Only real order fields are shown; a missing one is left out.
export function MoneyFlow({ run, className }: { run: Run; className?: string }) {
  if (!run.scorecard || run.status !== "completed" || run.live) return null;
  const o = run.order;
  const captured = o?.capture_status === "COMPLETED";

  if (!captured || !o) {
    if (!run.checkout) return null; // a browse-only check never tries to pay
    const lost = amountAtStake(run);
    return (
      <section className={cn("border bg-card p-6", className)} aria-label="Where the money went" data-testid="money-flow">
        <Card tone="bad" label={lost ? `Not captured: ${lost} lost` : "Not captured"} />
      </section>
    );
  }

  const cur = o.currency;
  const gross = money(o.gross_amount ?? o.amount, cur);
  const fee = o.paypal_fee ? money(o.paypal_fee, cur) : null;
  const net = o.net_amount ? money(o.net_amount, cur) : null;
  const refund = o.refund_status && o.refund_amount ? money(o.refund_amount, o.refund_currency || cur) : null;
  const children: Child[] = [
    fee && { label: "PayPal fee", value: `−${fee}` },
    net && { label: "Net to you", value: net },
    refund && { label: "Refunded", value: refund },
  ].filter(Boolean) as Child[];
  const height = children.length * CHILD_H + Math.max(children.length - 1, 0) * GAP;
  const mid = height / 2;
  const ys = children.map((_, i) => i * (CHILD_H + GAP) + CHILD_H / 2);

  return (
    <section className={cn("border bg-card p-6", className)} aria-label="Where the money went" data-testid="money-flow">
      <div className="flex flex-col gap-3 md:flex-row md:items-center md:gap-0">
        <Card label="Captured by PayPal" value={gross ?? undefined} className="md:w-60 md:shrink-0" />
        {children.length > 0 && (
          <>
            <svg aria-hidden className="hidden h-auto w-12 shrink-0 text-line md:block" width="48" height={height} viewBox={`0 0 48 ${height}`} preserveAspectRatio="none">
              {ys.map((y, i) => (
                <path key={i} d={`M0 ${mid} H24 V${y} H48`} fill="none" stroke="currentColor" strokeWidth="1.5" vectorEffect="non-scaling-stroke" />
              ))}
            </svg>
            <ul className="flex min-w-0 flex-1 flex-col" style={{ gap: GAP }}>
              {children.map((c) => (
                <li key={c.label}>
                  <Card label={c.label} value={c.value} className="md:h-[76px]" />
                </li>
              ))}
            </ul>
          </>
        )}
      </div>
    </section>
  );
}
