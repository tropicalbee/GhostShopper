import { ArrowRight } from "lucide-react";
import { memo } from "react";

import { MoneyDetails } from "@/components/YourMoney";
import type { Run, Scorecard } from "@/lib/api";
import { cn } from "@/lib/utils";

export type RingMark = "pass" | "fail";

// One segment per check: bright for a pass, dim for anything else.
export function ScoreRing({ marks, size, stroke, className }: { marks: RingMark[]; size: number; stroke: number; className?: string }) {
  const R = (size - stroke) / 2 - 2;
  const C = 2 * Math.PI * R;
  const gap = size > 220 ? 7 : 5;
  const len = C / marks.length - gap;
  return (
    <svg viewBox={`0 0 ${size} ${size}`} className={cn("-rotate-90", className)} aria-hidden>
      {marks.map((m, i) => (
        <circle
          key={i}
          cx={size / 2}
          cy={size / 2}
          r={R}
          fill="none"
          strokeWidth={stroke}
          stroke={m === "pass" ? "#ededed" : "#262626"}
          strokeDasharray={`${len} ${C - len}`}
          strokeDashoffset={-(i * (len + gap))}
        />
      ))}
    </svg>
  );
}

export function marksOf(run: Run): RingMark[] {
  return run.checks.map((c) => (c.status === "pass" ? "pass" : "fail"));
}

// The readiness score: the ring and a receipt-style sum of what each failed check cost. Points come from checks only.
export const ReadinessPanel = memo(function ReadinessPanel({ run, card, score, showAll }: { run: Run; card: Scorecard; score: number; showAll: boolean }) {
  const marks = marksOf(run);
  const passed = marks.filter((m) => m === "pass").length;
  return (
    <section className="glass overflow-hidden" aria-labelledby="readiness-h">
      <div className="panel-head">
        <div>
          <h3 id="readiness-h" className="text-[15px] font-medium tracking-[-0.02em]">
            Readiness score
          </h3>
          <p className="mt-0.5 text-[13px] text-faint">Where the agent got stuck. Points come from checks only.</p>
        </div>
      </div>
      <div className="grid sm:grid-cols-[210px_1fr]">
        <div className="relative grid place-items-center border-b p-[22px] sm:border-r sm:border-b-0">
          <ScoreRing marks={marks} size={200} stroke={10} className="size-[170px]" />
          <div className="absolute text-center">
            <div className="num text-[44px] leading-none font-medium tracking-[-0.06em]">{score}</div>
            <div className="mt-0.5 text-xs text-dim">
              {passed} of {marks.length} passed
            </div>
          </div>
        </div>
        <div className="num px-5 pt-2.5 pb-1.5 text-[13px]">
          <div className="grid grid-cols-[18px_1fr_auto] gap-2.5 border-b border-dashed border-[#262626] py-2.5">
            <span />
            <span>Points available</span>
            <span>{card.possible}</span>
          </div>
          {card.fixes.map((f) => (
            <div key={f.check} className="grid grid-cols-[18px_1fr_auto] gap-2.5 border-b border-dashed border-[#262626] py-2.5">
              <span className="text-dim">−</span>
              <span>
                {f.plain?.title ?? f.title}
                <small className="mt-0.5 block font-sans text-xs text-[#8a8a8a]">{f.status === "not_tested" ? "Not tested in this check." : (f.plain?.how ?? f.fix)}</small>
              </span>
              <span>{f.points}</span>
            </div>
          ))}
          <div className="mt-1 grid grid-cols-[18px_1fr_auto] gap-2.5 border-t-[1.5px] border-[#3a3a3a] py-2.5 font-medium">
            <span className="text-dim">=</span>
            <span>
              Points earned
              {card.possible !== 100 && <small className="mt-0.5 block font-sans text-xs font-normal text-[#8a8a8a]">Shown as {card.simple.score} out of 100.</small>}
            </span>
            <span>{card.total}</span>
          </div>
        </div>
      </div>
      <div className="flex items-center justify-between gap-3 border-t px-5 py-3 text-[12.5px] text-faint">
        <span>Not your store&apos;s fault: {card.not_store_fault.length ? `${card.not_store_fault.length} this check` : "nothing this check"}</span>
        {showAll && (
          <a href={`#/run/${run.id}/advanced`} className="inline-flex items-center gap-1.5 text-foreground no-underline">
            All {marks.length} checks <ArrowRight className="size-3.5" aria-hidden />
          </a>
        )}
      </div>
    </section>
  );
});

// Money for the run's own order: what PayPal took, the fee, the net, the order timeline and the test refund.
export function MoneyPanel({ run }: { run: Run }) {
  const o = run.order;
  return (
    <section className="glass overflow-hidden" aria-labelledby="money-h">
      <div className="panel-head">
        <div>
          <h3 id="money-h" className="text-[15px] font-medium tracking-[-0.02em]">
            Money
          </h3>
          <p className="mt-0.5 text-[13px] text-faint">{o ? `From the PayPal capture of order ${o.order_id}.` : "From the PayPal capture."}</p>
        </div>
        {o && <span className="rounded-full border border-[#2e2e2e] bg-[#1a1a1a] px-2.5 py-0.5 text-xs font-medium whitespace-nowrap text-foreground">{run.paypal_mode === "mock" ? "Practice payment" : "PayPal sandbox"}</span>}
      </div>
      <div className="px-5 pb-5">
        <MoneyDetails run={run} />
      </div>
    </section>
  );
}
