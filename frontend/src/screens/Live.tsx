import { CircleAlert, CircleCheck, Hand, Info, Loader2, Lock } from "lucide-react";
import { memo, useEffect, useState } from "react";

import { hostOf, Logo, ModeLabels, storeName } from "@/components/bits";
import { shotName, shotUrl, type FeedLine, type Run, type TraceStage } from "@/lib/api";
import { cn } from "@/lib/utils";

const TONE_WORD = { good: "Good", bad: "Costs points", info: "Note", neutral: "" } as const;
const ICON = { good: CircleCheck, bad: CircleAlert, info: Info, neutral: null } as const;

const clock = (ms: number) => {
  const s = Math.max(0, Math.round(ms / 1000));
  return `${String(Math.floor(s / 60)).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}`;
};

// A running timer, from the run's own start time.
function useElapsed(startedAt: string): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const t = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(t);
  }, []);
  return now - Date.parse(startedAt);
}

// Each poll returns fresh objects for lines that have not changed, so compare by content, not identity.
// A new line then renders alone instead of the whole feed re-rendering (and re-running its entry animation).
const Line = memo(
  function Line({ line, at }: { line: FeedLine; at: string | null }) {
    const Icon = ICON[line.tone];
    return (
      <li className={cn("slide-in grid grid-cols-[2rem_1.25rem_minmax(0,1fr)_auto] items-start gap-2.5 rounded-lg px-3 py-2.5 text-[13.5px] sm:grid-cols-[2.75rem_1.25rem_minmax(0,1fr)_auto]", line.tone === "bad" && "bg-gradient-to-r from-[#161616] to-[#0b0b0b] shadow-[inset_0_0_0_1px_#2e2e2e]")}>
        <span className="num pt-px text-[11.5px] text-dim">{String(line.step).padStart(2, "0")}</span>
        {Icon ? <Icon className={cn("mt-px size-4", line.tone === "bad" ? "text-foreground" : "text-muted-foreground")} aria-label={TONE_WORD[line.tone]} /> : <span />}
        <span className={line.tone === "neutral" ? "text-muted-foreground" : undefined}>
          {line.text}
          {line.tone === "bad" && <small className="mt-px block text-xs text-[#8a8a8a]">This costs points.</small>}
          {line.tone === "info" && <small className="mt-px block text-xs text-[#8a8a8a]">Not your store&apos;s fault.</small>}
        </span>
        <span className="num pt-px text-[11.5px] text-dim">{at}</span>
      </li>
    );
  },
  (a, b) => a.line.step === b.line.step && a.line.text === b.line.text && a.line.tone === b.line.tone && a.at === b.at,
);

const LABEL: Record<TraceStage["key"], string> = {
  agent_wanted: "01 AGENT WANTED",
  store_order: "02 STORE ORDER",
  paypal_order: "03 PAYPAL ORDER",
  paypal_capture: "04 PAYPAL CAPTURE",
  store_says: "05 STORE SAYS",
};

// The trace prints as each record becomes known: a stage with a readable value shows it, the rest wait.
function Receipt({ run }: { run: Run }) {
  const stages = run.trace.stages;
  const known = (s: TraceStage) => Object.values(s.cells).some((c) => c.kind === "known");
  const current = stages.find((s) => !known(s))?.key;
  const wanted = stages[0].cells.product;
  const name = (sku: string) => (wanted.kind === "known" && String(wanted.value) === sku && run.target_product ? run.target_product : sku);
  return (
    <div className="flex flex-col items-center pt-[22px] pb-[30px]">
      <div className="relative z-[2] h-4 w-[296px] max-w-full rounded-[7px] border border-[#333] bg-gradient-to-b from-[#202020] to-[#070707] shadow-[inset_0_-5px_8px_rgba(0,0,0,0.9)]" />
      <div className="paper -mt-1.5 w-[262px] max-w-[calc(100%-24px)] px-4 pt-[18px] pb-3.5 text-[10.5px] leading-4 shadow-[0_18px_40px_rgba(0,0,0,0.6)]">
        <div className="text-center font-medium tracking-[0.12em]">
          <Logo className="mx-auto mb-[3px] size-[18px]" />
          PURCHASE TRACE
        </div>
        <div className="dash" />
        {stages.map((s) => {
          const ok = known(s);
          const c = s.cells;
          const detail = [c.product.kind === "known" && name(String(c.product.value)), c.quantity.kind === "known" && c.amount.kind === "known" && `${c.quantity.value} × ${c.amount.value}`, c.status.kind === "known" && s.key !== "agent_wanted" && String(c.status.value)].filter(Boolean);
          return (
            <div key={s.key} className={cn("mb-1.5", ok && "print-line")}>
              <div className="flex justify-between gap-2">
                <span className={cn("font-medium", !ok && s.key !== current && "text-[#999]")}>{LABEL[s.key]}</span>
                <span className={ok ? undefined : "tracking-[0.1em] text-[#999]"}>{ok ? "ok" : "· · ·"}</span>
              </div>
              {ok && detail.length > 0 && <div className="break-words text-[#444]">{detail.join(" · ")}</div>}
            </div>
          );
        })}
        <div className="tear" />
      </div>
    </div>
  );
}

export function Live({ run }: { run: Run }) {
  const elapsed = useElapsed(run.started_at);
  const withShot = [...run.steps].reverse().find((s) => shotName(s.screenshot_path));
  const shot = withShot && shotName(withShot.screenshot_path);
  const url = [...run.steps].reverse().find((s) => s.url)?.url ?? run.store_url;
  const atOf = (step: number) => {
    const s = run.steps.find((x) => x.idx === step);
    return s ? clock(Date.parse(s.created_at) - Date.parse(run.started_at)) : null;
  };
  const passed = run.checks.filter((c) => c.status === "pass").length;
  const costing = run.checks.filter((c) => c.status === "fail").length;
  const notFault = run.checks.filter((c) => c.status === "excluded").length;
  const feed = [...run.feed].reverse();
  const human = run.status === "awaiting_human" && run.awaiting;

  return (
    <div>
      <header className="mt-1.5">
        <h1 className="text-2xl leading-[1.2] font-medium tracking-[-0.035em] text-balance sm:text-[28px]">
          {run.live ? `The shopper is browsing ${storeName(run)}.` : `The shopper is buying the ${run.target_product}.`}
        </h1>
        <div className="mt-2.5 flex flex-wrap items-center gap-x-2.5 gap-y-1.5 text-[13.5px] text-faint">
          <span className="num inline-flex items-center gap-2 text-[13px] font-medium text-foreground">
            <span className="size-[7px] rounded-full bg-foreground shadow-[0_0_0_4px_rgba(255,255,255,0.08)]" aria-hidden />
            {clock(elapsed)}
          </span>
          <span>· {hostOf(run.store_url)}</span>
          <span>· step {run.steps.length}</span>
          <ModeLabels run={run} />
        </div>
      </header>

      <div className="mt-6 grid items-start gap-5 lg:grid-cols-[minmax(0,1fr)_340px]">
        <div>
          <section className="glass overflow-hidden" aria-label="What the browser sees">
            <div className="flex items-center gap-3 border-b px-3.5 py-2.5">
              <span className="hidden gap-1.5 sm:flex" aria-hidden>
                {[0, 1, 2].map((i) => (
                  <i key={i} className="size-[9px] rounded-full bg-[#2a2a2a]" />
                ))}
              </span>
              <span className="num flex h-[30px] min-w-0 flex-1 items-center gap-2 rounded-lg border border-[#1f1f1f] bg-[#0b0b0b] px-3 text-[12.5px] text-muted-foreground">
                <Lock className="size-[13px] shrink-0 text-dim" aria-hidden />
                <span className="truncate">{url}</span>
              </span>
              <span className="num hidden text-xs text-faint sm:block">live view · step {withShot?.idx ?? 0}</span>
            </div>
            <div className="relative h-[430px] overflow-hidden bg-[#0a0a0a] max-sm:h-64">
              {shot ? (
                <img src={shotUrl(run.id, shot)} alt={`What the browser saw at step ${withShot?.idx}`} className="absolute inset-0 size-full object-cover object-top" />
              ) : (
                <p className="grid h-full place-items-center text-sm text-muted-foreground">Waiting for the first screenshot…</p>
              )}
            </div>
            <div className="flex justify-between border-t px-3.5 py-2.5 text-[12.5px] text-faint">
              <span>Screenshot of what the browser saw at its last step</span>
            </div>
          </section>

          {human && run.awaiting && (
            <section className="glass mt-5 grid items-center gap-4 p-5 sm:grid-cols-[auto_1fr_auto]">
              <span className="grid size-10 place-items-center rounded-[10px] border border-[#2e2e2e] bg-[#141414]">
                <Hand className="size-[18px]" aria-hidden />
              </span>
              <div>
                <h3 className="text-[15px] font-medium">PayPal needs a person for a moment.</h3>
                <p className="mt-1 text-[13px] text-muted-foreground">
                  {run.awaiting.reason} {run.awaiting.instructions}
                </p>
              </div>
              {run.awaiting.live_view_url ? (
                <a href={run.awaiting.live_view_url} target="_blank" rel="noreferrer" className="shine inline-flex h-9 items-center justify-center rounded-lg bg-foreground px-3.5 text-[13.5px] font-medium whitespace-nowrap text-[#0a0a0a] no-underline">
                  Open the shopper&apos;s browser
                </a>
              ) : (
                <p className="text-[13px] text-faint sm:max-w-[220px]">This check needs a person and will stop.</p>
              )}
            </section>
          )}

          <section className="glass mt-5">
            <div className="panel-head">
              <div>
                <h3 className="text-[15px] font-medium tracking-[-0.02em]">What the shopper is doing</h3>
                <p className="mt-0.5 text-[13px] text-faint">Every step keeps its screenshot.</p>
              </div>
            </div>
            <ol aria-live="polite" aria-label="What the shopper is doing" className="px-2 pt-1.5 pb-2.5">
              {feed.map((line) => (
                <Line key={`${line.step}-${line.text}`} line={line} at={atOf(line.step)} />
              ))}
              {!feed.length && (
                <li className="flex items-center gap-2.5 px-3 py-2.5 text-[13.5px] text-muted-foreground">
                  <Loader2 className="size-4 animate-spin" aria-hidden />
                  Opening the store…
                </li>
              )}
            </ol>
          </section>
        </div>

        <aside className="grid gap-5">
          <section className="glass">
            <div className="panel-head">
              <div>
                <h3 className="text-[15px] font-medium tracking-[-0.02em]">Purchase trace</h3>
                <p className="mt-0.5 text-[13px] text-faint">Prints as each record is read.</p>
              </div>
            </div>
            <Receipt run={run} />
          </section>
          <section className="glass">
            <div className="panel-head">
              <h3 className="text-[15px] font-medium tracking-[-0.02em]">So far</h3>
            </div>
            <dl className="px-5 pt-1 pb-4.5 text-[13.5px]">
              {(
                [
                  ["Checks passed", passed],
                  ["Costing points", costing],
                  ["Not your store's fault", notFault],
                ] as const
              ).map(([label, n]) => (
                <div key={label} className="flex justify-between border-b py-2.5 last:border-b-0">
                  <dt className="text-faint">{label}</dt>
                  <dd className="num font-medium">{n}</dd>
                </div>
              ))}
            </dl>
          </section>
        </aside>
      </div>
    </div>
  );
}
