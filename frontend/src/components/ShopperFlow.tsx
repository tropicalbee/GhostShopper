import { ArrowRight, Check, Minus, X } from "lucide-react";
import { Fragment, useMemo } from "react";

import { blockingCheck } from "@/components/bits";
import type { Run } from "@/lib/api";
import { money } from "@/lib/compare";
import { cn } from "@/lib/utils";

type State = "pass" | "fail" | "untested";

// The shopper's way to paying, as cards. Each card is a group of rubric checks (keys from scoring.py).
const FLOW: { key: string; name: string; checks: string[] }[] = [
  { key: "find", name: "Find product", checks: ["product_found"] },
  { key: "page", name: "Product page", checks: ["price_in_text", "structured_data", "stock_readable"] },
  { key: "checkout", name: "Checkout", checks: ["clear_buy_button", "buy_button_unobstructed", "checkout_reached", "no_extra_steps", "paypal_button_found"] },
  { key: "paypal", name: "PayPal", checks: ["popup_opened", "payment_approved"] },
  { key: "captured", name: "Captured", checks: ["capture_completed"] },
  { key: "verified", name: "Verified in PayPal", checks: ["payment_verified"] },
];

function stateOf(run: Run, keys: string[]): State {
  const statuses = run.checks.filter((c) => keys.includes(c.check_key)).map((c) => c.status);
  if (statuses.includes("fail")) return "fail";
  return statuses.includes("pass") ? "pass" : "untested";
}

// What the sale is worth, by the same rules as MoneyHero: the demo store's catalog price, else the order amount.
export function amountAtStake(run: Run): string | null {
  if (!run.live && run.catalog_price) return money(run.catalog_price.amount, run.catalog_price.currency);
  return run.order?.amount ? money(run.order.amount, run.order.currency) : null;
}

const STATE_TEXT: Record<State, string> = { pass: "Pass", fail: "Fail", untested: "Not tested" };

// Razorpay-style card chain: square cards, small uppercase labels, thin connectors. Wraps to a column on phones.
export function ShopperFlow({ run, className }: { run: Run; className?: string }) {
  const cards = useMemo(() => {
    const states = FLOW.map((f) => stateOf(run, f.checks));
    const blocker = blockingCheck(run);
    return { states, blocker, stop: blocker ? FLOW.findIndex((f) => f.checks.includes(blocker.key)) : -1 };
  }, [run]);
  if (!run.scorecard || run.status !== "completed") return null;
  const { states, stop, blocker } = cards;
  const stake = amountAtStake(run);

  return (
    <section className={cn("border bg-card p-6", className)} aria-labelledby="shopper-flow" data-testid="shopper-flow">
      <p id="shopper-flow" className="text-[11px] font-medium tracking-[0.12em] text-muted-foreground uppercase">
        The AI shopper's way to paying
      </p>
      <ol className="mt-4 flex flex-col gap-2 lg:flex-row lg:items-stretch lg:gap-0">
        {FLOW.map((f, i) => {
          const state = states[i];
          const stopped = i === stop;
          const greyed = stop >= 0 && i > stop;
          const passedOver = state === "fail" && !stopped && !greyed; // a failure the shopper got past
          const Icon = state === "pass" ? Check : state === "fail" ? X : Minus;
          return (
            <Fragment key={f.key}>
              <li
                className={cn(
                  "flex min-w-0 flex-1 flex-col border-[1.5px] px-3 py-3",
                  stopped ? "border-bad bg-bad/5" : passedOver ? "border-warn" : "border-foreground/80",
                  greyed && "border-line opacity-50",
                )}
                aria-current={stopped ? "step" : undefined}
                data-state={greyed ? "skipped" : state}
              >
                <span className="text-[11px] font-medium tracking-[0.12em] text-muted-foreground uppercase">{f.name}</span>
                <span
                  className={cn(
                    "mt-2 inline-flex items-center gap-1.5 text-sm font-semibold",
                    greyed ? "text-muted-foreground" : state === "pass" ? "text-good" : passedOver ? "text-warn" : state === "fail" ? "text-bad" : "text-muted-foreground",
                  )}
                >
                  <Icon className="size-4" aria-hidden />
                  {STATE_TEXT[state]}
                </span>
                {passedOver && <span className="mt-2 text-[13px] leading-snug font-medium text-warn">Got past</span>}
                {stopped && (
                  <span className="mt-2 text-[13px] leading-snug font-medium text-bad">
                    Stopped here
                    {blocker && <span className="block font-normal text-foreground">{blocker.title}</span>}
                    {stake && <span className="num block font-normal">{stake} at stake</span>}
                  </span>
                )}
              </li>
              {i < FLOW.length - 1 && (
                <li aria-hidden className="grid place-items-center text-muted-foreground lg:w-6">
                  <ArrowRight className="hidden size-3.5 lg:block" />
                  <span className="mx-auto block h-3 w-px bg-line lg:hidden" />
                </li>
              )}
            </Fragment>
          );
        })}
      </ol>
    </section>
  );
}
