import { blockingCheck } from "@/components/bits";
import type { Run } from "@/lib/api";
import { cn } from "@/lib/utils";

const format = (value: string | number, currency: string) => {
  try {
    return new Intl.NumberFormat("en-US", { style: "currency", currency }).format(Number(value));
  } catch {
    return null; // not a currency code Intl knows: show nothing rather than guess
  }
};

// Where the shopper stopped, in words a merchant uses. Keys follow STAGES in bits.tsx.
const STOPPED_AT: Record<string, string> = {
  discover: "finding the product",
  details: "reading the product details",
  checkout: "checkout",
  payment: "the PayPal payment",
  outcome: "finishing the order",
};

// What ended the run (see blockingCheck): where, the plain reason and fix, and how many earlier problems the shopper got past.
function stoppedAt(run: Run): { where: string; why: string; fix: string | null; past: number } | null {
  const b = blockingCheck(run);
  if (!b) return null;
  const where = b.key === "paypal_button_found" ? "checkout, before the PayPal button" : (STOPPED_AT[b.stage] ?? b.stage);
  return { where, why: b.title, fix: b.fix, past: b.obstacles };
}

// What the product costs: the demo store's catalog price, else the order PayPal was asked for, else the price the shopper read.
function productAmount(run: Run): string | null {
  if (!run.live && run.catalog_price) return format(run.catalog_price.amount, run.catalog_price.currency);
  const o = run.order;
  if (o?.amount) return format(o.amount, o.currency);
  const price = run.product_feed?.row?.price;
  const match = price?.match(/^(\d+(?:\.\d+)?)\s+([A-Z]{3})$/);
  return match ? format(match[1], match[2]) : null;
}

function productName(run: Run): string | null {
  return run.target_product || run.product_feed?.row?.title || null;
}

// The first thing on a finished check: can an AI shopper pay this store through PayPal, and what did it cost to find out.
export function MoneyHero({ run, className }: { run: Run; className?: string }) {
  if (!run.scorecard || run.status !== "completed") return null;
  const o = run.order;
  const captured = o?.capture_status === "COMPLETED";
  const practice = run.paypal_mode === "mock";

  if (captured && o) {
    const gross = o.gross_amount ?? o.amount;
    const paid = format(gross, o.currency);
    const fee = o.paypal_fee ? format(o.paypal_fee, o.currency) : null;
    const net = o.net_amount ? format(o.net_amount, o.currency) : null;
    const refunded = o.refund_status ? (o.refund_amount ? format(o.refund_amount, o.refund_currency || o.currency) : null) : null;
    const parts = [paid && `${paid} captured`, fee && `${fee} PayPal fee`, net && `${net} net to you`].filter(Boolean);
    // The agent got through, but every failed check was a place a less patient agent could have left.
    const obstacles = run.scorecard.fixes.filter((f) => f.status === "failed").length;
    const atRisk = obstacles > 0 ? productAmount(run) : null;
    return (
      <section className={cn("border bg-card p-6", obstacles > 0 ? "border-bad/40" : "border-good/40", className)} aria-labelledby="money-hero" data-testid="money-hero">
        <p className="text-[13px] text-muted-foreground">Can an AI agent actually pay you through PayPal?</p>
        <h2 id="money-hero" className="mt-1 text-2xl leading-snug font-semibold tracking-[-0.02em]">
          {obstacles > 0 ? "Paid with PayPal" : "Yes. Paid with PayPal"}
          {practice ? " (practice mode)" : ""}
          {parts.length > 0 ? `: ${parts.join(", ")}` : ""}.
        </h2>
        {obstacles > 0 && (
          <p className="mt-2 text-lg font-medium text-bad" data-testid="money-hero-risk">
            Our agent got through after {obstacles} {obstacles === 1 ? "obstacle" : "obstacles"}. A less patient AI agent would have left
            {atRisk ? `: ${atRisk} at risk` : ""}.
          </p>
        )}
        {o.refund_status && (
          <p className="mt-2 text-sm text-muted-foreground">
            Refund {o.refund_status.toLowerCase()}
            {refunded ? `: ${refunded} returned` : ""}.
          </p>
        )}
      </section>
    );
  }

  const stop = stoppedAt(run);
  if (!stop) return null;
  const name = productName(run);
  const amount = productAmount(run);
  return (
    <section className={cn("border border-bad/40 bg-card p-6", className)} aria-labelledby="money-hero" data-testid="money-hero">
      <p className="text-[13px] text-muted-foreground">Can an AI agent actually pay you through PayPal?</p>
      <h2 id="money-hero" className="mt-1 text-2xl leading-snug font-semibold tracking-[-0.02em]">
        No. The AI shopper tried to buy {name ?? "a product"} and stopped at {stop.where}.
        {amount && !run.live ? ` You lost ${amount}.` : ""}
      </h2>
      <p className="mt-2 text-muted-foreground">
        {stop.why}.{stop.fix ? ` ${stop.fix}` : ""}
      </p>
      {stop.past > 0 && (
        <p className="mt-2 text-muted-foreground">
          It got past {stop.past} other {stop.past === 1 ? "problem" : "problems"} first.
        </p>
      )}
    </section>
  );
}
