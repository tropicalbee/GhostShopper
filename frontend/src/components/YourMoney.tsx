import { Check, X } from "lucide-react";
import { useState } from "react";

import { Label } from "@/components/bits";
import { RefundTest, refundedOf } from "@/components/RefundTest";
import type { Order, Refund, Run } from "@/lib/api";
import { cn } from "@/lib/utils";

const money = (value: string | null, currency: string) =>
  value == null ? "Not reported" : new Intl.NumberFormat("en-US", { style: "currency", currency }).format(Number(value));

function when(iso: string | null | undefined) {
  if (!iso) return null;
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return null;
  return d.toLocaleString(undefined, { month: "short", day: "numeric", hour: "numeric", minute: "2-digit", second: "2-digit" });
}

type Moment = { label: string; detail: string; at: string | null; state: "done" | "bad" | "waiting" };

function timeline(o: Order, refund: Refund | null): Moment[] {
  const captured = o.capture_status === "COMPLETED";
  const out: Moment[] = [
    { label: "Order created", detail: `${money(o.amount, o.currency)} asked for`, at: when(o.created_at), state: "done" },
    captured
      ? { label: "Payment captured", detail: `${money(o.gross_amount ?? o.amount, o.currency)} received`, at: when(o.captured_at), state: "done" }
      : { label: "Payment not captured", detail: o.capture_status ? `PayPal says ${o.capture_status.toLowerCase()}` : "No money moved", at: null, state: "bad" },
  ];
  if (captured && refund) {
    out.push({
      label: "Refunded",
      detail: `${money(refund.amount, refund.currency || o.currency)}, ${refund.verified ? "verified against PayPal" : "does not match the payment"}`,
      at: when(refund.refunded_at ?? o.refunded_at),
      state: refund.verified ? "done" : "bad",
    });
  } else if (captured) {
    out.push({ label: "Refunded", detail: "Not refunded", at: null, state: "waiting" });
  }
  return out;
}

// The spending limit the shopper was given and what happened to it. Null when the run had no limit.
function BudgetLine({ run }: { run: Run }) {
  if (!run.budget || !run.checkout) return null;
  const limit = money(run.budget, "USD");
  const stopped = run.checks.find((c) => c.code === "over_budget");
  const o = run.order;
  let text = `Spending limit ${limit}`;
  let tone = "text-muted-foreground";
  if (stopped) {
    const total = stopped.evidence?.checkout_total;
    text = typeof total === "string" ? `Stopped: ${money(total, "USD")} is over the ${limit} limit` : `Stopped: the total could not be read to check the ${limit} limit`;
    tone = "text-warn";
  } else if (o?.capture_status === "COMPLETED") {
    const paid = money(o.gross_amount ?? o.amount, o.currency);
    const within = Number(o.gross_amount ?? o.amount) <= Number(run.budget);
    text = within ? `Bought for ${paid} within a ${limit} limit` : `Bought for ${paid}, over the ${limit} limit`;
    tone = within ? "text-good" : "text-bad";
  }
  return (
    <p className={cn("mt-3 text-sm font-medium", tone)} data-testid="budget-line">
      {text}
    </p>
  );
}

function Figure({ label, value, strong }: { label: string; value: string; strong?: boolean }) {
  return (
    <div className="border-b py-2.5 sm:border-b-0">
      <dt className="text-[13px] text-muted-foreground">{label}</dt>
      <dd className={cn("num mt-0.5", strong ? "text-2xl font-medium tracking-tight" : "text-lg")}>{value}</dd>
    </div>
  );
}

function Body({ run, order: o }: { run: Run; order: Order }) {
  const [refund, setRefund] = useState<Refund | null>(() => refundedOf(o));
  const captured = o.capture_status === "COMPLETED";
  const gross = o.gross_amount ? Number(o.gross_amount) : null;
  const fee = o.paypal_fee ? Number(o.paypal_fee) : null;
  const percent = gross && fee != null ? `${((fee / gross) * 100).toFixed(2)}%` : "Not reported";
  const steps = timeline(o, refund);
  return (
    <>
      {captured ? (
        <dl className="mt-4 grid grid-cols-2 gap-x-8">
          <Figure label="Customer paid" value={money(o.gross_amount, o.currency)} />
          <Figure label="PayPal fee" value={o.paypal_fee ? `−${money(o.paypal_fee, o.currency)}` : "Not reported"} />
          <Figure label="You keep" value={money(o.net_amount, o.currency)} strong />
          <Figure label="Effective fee" value={percent} />
        </dl>
      ) : (
        <p className="mt-3 text-muted-foreground">The order was created but PayPal did not capture a payment, so there are no fees to show.</p>
      )}
      <p className="mt-1 text-[13px] text-muted-foreground">Currency {o.currency}. Figures are the ones PayPal returned when the payment was captured.</p>

      <ol className="mt-5 border-t" aria-label="Order timeline">
        {steps.map((s) => (
          <li key={s.label} className="grid grid-cols-[1.25rem_minmax(0,1fr)_auto] items-baseline gap-x-3 border-b py-2.5 text-sm">
            <span className={cn("self-center", s.state === "done" && "text-good", s.state === "bad" && "text-bad", s.state === "waiting" && "text-muted-foreground")} aria-hidden>
              {s.state === "done" ? <Check className="size-4" /> : s.state === "bad" ? <X className="size-4" /> : <span className="block size-2 border border-current" />}
            </span>
            <span className={cn(s.state === "waiting" && "text-muted-foreground")}>
              <span className="font-medium">{s.label}</span>
              <span className="text-muted-foreground">. {s.detail}</span>
            </span>
            <span className="num text-[12px] text-muted-foreground">{s.at}</span>
          </li>
        ))}
      </ol>

      {captured && run.mine && !refund && (
        <>
          <RefundTest key={o.order_id} orderId={o.order_id} currency={o.currency} refunded={null} onRefunded={setRefund} showResult={false} />
          <p className="mt-2 text-[13px] text-muted-foreground">Gives the full test payment back through PayPal and checks the money returned. It does not change the score.</p>
        </>
      )}
      {refund && !refund.verified && <ul className="mt-2 text-sm text-bad">{refund.mismatches.map((m) => <li key={m}>{m}</li>)}</ul>}
    </>
  );
}

// The money details for the run's own order: spending limit, what the customer paid, what PayPal kept, the order
// timeline and the test refund. Shown inside the Money panel on Results.
export function MoneyDetails({ run }: { run: Run }) {
  const o = run.order;
  const running = run.status === "running" || run.status === "awaiting_human";
  return (
    <>
      <BudgetLine run={run} />
      {o ? (
        <Body key={o.order_id} run={run} order={o} />
      ) : (
        <p className="mt-3 text-muted-foreground">
          {run.live
            ? "We never pay on real stores, so there is no payment to show."
            : running
              ? "The payment will show up here if the shopper buys something."
              : run.checkout
                ? "The shopper did not pay in this check, so no money moved."
                : "This check did not include a payment."}
        </p>
      )}
    </>
  );
}

// Money for the run's own order as its own card. Results shows MoneyDetails in the Money panel instead.
export function YourMoney({ run, className }: { run: Run; className?: string }) {
  const practice = run.paypal_mode === "mock";
  return (
    <section className={cn("border bg-card p-6", className)} aria-labelledby="your-money">
      <Label className="text-[15px]" aside={run.order ? (practice ? "Practice payment, not PayPal" : "PayPal sandbox payment") : undefined}>
        <span id="your-money">Your money</span>
      </Label>
      <MoneyDetails run={run} />
    </section>
  );
}
