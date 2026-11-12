import { ArrowRight, ChevronRight, RotateCw, ShieldAlert, Store } from "lucide-react";
import { memo, useMemo, useState } from "react";

import { checkedAt, hostOf, ModeLabels, StatusLine, storeName } from "@/components/bits";
import { DeveloperDialog, ShowMeDialog } from "@/components/dialogs";
import { CompareGrid } from "@/components/CompareGrid";
import { PayPalReadiness } from "@/components/PayPalReadiness";
import { ProductFeedLine } from "@/components/ProductFeedLine";
import { MoneyPanel, ReadinessPanel } from "@/components/ReadinessPanels";
import { HEAD, TraceTable, type Evidence } from "@/components/TraceTable";
import { Button } from "@/components/ui/button";
import { PathCompareTable, WebMCPPanels, WebMCPStrip } from "@/components/WebMCP";
import { api, ApiError, sameSeries, shotName, shotUrl, startCheck, type Health, type PlainFix, type Run, type RunSummary } from "@/lib/api";
import { fetchCompare } from "@/lib/compare";
import { go, useCountUp, useFetch } from "@/lib/hooks";
import { cn, stripLocalOrigin } from "@/lib/utils";

// Results re-renders on each frame of the score count-up; the fix list does not change, so skip it.
const FixItem = memo(function FixItem({ fix, n }: { fix: PlainFix; n: number }) {
  return (
    <li className="grid grid-cols-[2rem_minmax(0,1fr)] gap-x-3 border-b py-6 last:border-b-0">
      <span className="num grid size-7 place-items-center rounded-md border border-[#2e2e2e] text-[13px] text-foreground/80" aria-hidden>
        {n}
      </span>
      <div>
        <h3 className="text-[17px] leading-snug font-semibold tracking-[-0.01em]">{fix.title}</h3>
        <p className="mt-1 text-muted-foreground">{stripLocalOrigin(fix.why)}</p>
        <div className="mt-4 rounded-lg border bg-panel px-4 py-3">
          <p className="text-[13px] font-semibold">How to fix it</p>
          <p className="mt-0.5">{stripLocalOrigin(fix.steps ?? fix.how)}</p>
        </div>
        {fix.screenshot_url && (
          <div className="mt-2">
            <ShowMeDialog src={fix.screenshot_url} title={fix.title} />
          </div>
        )}
      </div>
    </li>
  );
});

const PURCHASE: Record<string, string> = {
  purchased: "Paid",
  reached_checkout: "Not paid",
  blocked: "Payment failed",
  gave_up: "Stopped before paying",
  error: "Didn't finish",
};

const OUTCOME_SENTENCE: Record<string, string> = {
  purchased: "The purchase went through.",
  reached_checkout: "The shopper reached checkout but did not pay.",
  blocked: "The payment didn't go through.",
  gave_up: "The shopper gave up before paying.",
  error: "The check didn't finish.",
};

// One sentence on what happened to the purchase, from the trace and the outcome.
function verdict(run: Run): string {
  const first = run.trace.first_mismatch;
  if (first) return first.explanation.split(/(?<=\.)\s/)[0];
  if (run.live) return `Browsed ${hostOf(run.store_url)} up to the PayPal button. Nothing was paid.`;
  const base = OUTCOME_SENTENCE[run.outcome ?? ""] ?? "The check is done.";
  if (run.outcome !== "purchased") return base;
  const unknown = run.trace.counts.unknown;
  return unknown ? `${base} Every record we could read agrees, and ${unknown} could not be read.` : `${base} Every record agrees.`;
}

const clock = (ms: number) => {
  const s = Math.max(0, Math.round(ms / 1000));
  return `${String(Math.floor(s / 60)).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}`;
};

function Strip({ run, score, cost }: { run: Run; score: number; cost: number }) {
  const o = run.order;
  const first = run.trace.first_mismatch;
  const captured = o?.capture_id ? Number(o.gross_amount ?? o.amount).toFixed(2) : null;
  const seconds = run.finished_at ? Math.round((Date.parse(run.finished_at) - Date.parse(run.started_at)) / 1000) : null;
  const cell = "relative px-5 py-[18px] [&_small]:block [&_small]:text-xs [&_small]:text-faint [&_b]:mt-1.5 [&_b]:block [&_b]:text-lg [&_b]:font-medium [&_b]:tracking-[-0.02em] [&_span.sub]:mt-[3px] [&_span.sub]:block [&_span.sub]:text-[12.5px] [&_span.sub]:text-[#8a8a8a]";
  return (
    <div className="glass grid grid-cols-2 lg:grid-cols-4" role="group" aria-label="Summary">
      <div className={cell}>
        <small>Purchase</small>
        <b className="flex flex-wrap items-center gap-2">
          {run.live ? "Browse only" : (PURCHASE[run.outcome ?? ""] ?? "Unknown")}
          {first && <span className="rounded-full border border-[#9a9a9a] bg-[#0a0a0a] px-2.5 py-0.5 text-xs font-medium text-white shadow-[0_0_14px_rgba(255,255,255,0.16)]">Mismatch</span>}
        </b>
        <span className="sub">{first ? `First mismatch at ${HEAD[first.stage]}` : run.trace.counts.unknown ? `${run.trace.counts.unknown} unknown` : "No mismatch found"}</span>
      </div>
      <div className={cn(cell, "border-l")}>
        <small>Money</small>
        <b className="num">{captured ? `${captured} ${o?.currency} captured` : "Nothing captured"}</b>
        <span className="sub">{o?.paypal_fee && o.net_amount ? `Fee ${Number(o.paypal_fee).toFixed(2)} · net ${Number(o.net_amount).toFixed(2)}` : "No payment in this check"}</span>
      </div>
      <div className={cn(cell, "border-t border-l-0 lg:border-t-0 lg:border-l")}>
        <small>Readiness</small>
        <b>
          {score} <span className="text-sm text-dim">/ 100</span>
        </b>
        <span className="sub">{cost ? `${cost} ${cost === 1 ? "check costs" : "checks cost"} points` : "No check costs points"}</span>
      </div>
      <div className={cn(cell, "border-t border-l lg:border-t-0")}>
        <small>Shopper</small>
        <b>{run.outcome === "error" ? "Stopped early" : `${run.steps.length} steps`}</b>
        <span className="sub">{seconds != null ? `${seconds} s` : "Still running"}</span>
      </div>
    </div>
  );
}

function PathStrip({ run }: { run: Run }) {
  const items = run.steps.flatMap((s) => {
    const name = shotName(s.screenshot_path);
    return name ? [{ step: s, name }] : [];
  });
  if (!items.length) return null;
  return (
    <section className="glass mt-5 overflow-hidden" aria-labelledby="path-h">
      <div className="panel-head">
        <div>
          <h3 id="path-h" className="text-[15px] font-medium tracking-[-0.02em]">
            The shopper&apos;s path
          </h3>
          <p className="mt-0.5 text-[13px] text-faint">{run.steps.length} steps, each with the screenshot of what the browser saw.</p>
        </div>
      </div>
      <ol className="flex gap-3 overflow-x-auto px-5 pt-[18px] pb-5 [scrollbar-color:#333_transparent] [scrollbar-width:thin]">
        {items.map(({ step, name }) => {
          const line = run.feed.find((l) => l.step === step.idx);
          const flagged = line?.tone === "bad";
          return (
            <li key={step.idx} className="w-[180px] flex-none">
              <a href={shotUrl(run.id, name)} target="_blank" rel="noreferrer" className="block no-underline">
                <span className={cn("relative block h-28 overflow-hidden rounded-lg border border-[#262626] bg-[#0b0b0b]", flagged && "shadow-[inset_0_0_0_1px_#6a6a6a]")}>
                  <img src={shotUrl(run.id, name)} alt={`Step ${step.idx}: ${line?.text ?? step.tool}`} loading="lazy" className="size-full object-cover object-top" />
                  {flagged && <span className="num absolute right-1.5 bottom-1.5 rounded bg-foreground px-1.5 py-[3px] text-[10px] leading-none font-medium text-black">Costs points</span>}
                </span>
                <span className="mt-2 flex justify-between gap-2 text-[12.5px] text-foreground">
                  <span className="min-w-0 truncate">{line?.text ?? step.tool.replaceAll("_", " ")}</span>
                  <span className="num shrink-0 text-[11px] text-dim">{clock(Date.parse(step.created_at) - Date.parse(run.started_at))}</span>
                </span>
              </a>
            </li>
          );
        })}
      </ol>
    </section>
  );
}

function SafetyPanel({ run }: { run: Run }) {
  const { findings, followed } = run.agent_safety;
  if (!findings.length) return null;
  return (
    <section className="glass mt-5 overflow-hidden" aria-labelledby="safety-h">
      <div className="panel-head">
        <div>
          <h3 id="safety-h" className="flex items-center gap-2 text-[15px] font-medium tracking-[-0.02em]">
            <ShieldAlert className="size-4" aria-hidden />
            Instructions aimed at AI shoppers
          </h3>
          <p className="mt-0.5 text-[13px] text-faint">
            Your store has text meant for an AI agent, not for people. {followed ? "The shopper followed at least one of them." : "The shopper did not follow any of them."}
          </p>
        </div>
      </div>
      <ul>
        {findings.map((f, i) => (
          <li key={i} className="grid gap-3 border-b px-5 py-4 last:border-b-0 sm:grid-cols-[1fr_auto]">
            <div className="min-w-0">
              <p className="flex flex-wrap items-center gap-2 text-[13px] text-faint">
                <span className="num break-all">{f.where}</span>
                <span className={cn("rounded-full border px-2 py-0.5 text-xs font-medium", f.hidden ? "border-[#9a9a9a] bg-[#0a0a0a] text-white" : "border-[#262626] bg-[#141414] text-muted-foreground")}>
                  {f.hidden ? "Hidden from people" : "Visible on the page"}
                </span>
              </p>
              <p className="mt-2 rounded-lg border bg-panel px-3 py-2 text-[13.5px] break-words text-muted-foreground">&ldquo;{f.excerpt}&rdquo;</p>
            </div>
            {shotName(f.screenshot) && (
              <a href={shotUrl(run.id, shotName(f.screenshot)!)} target="_blank" rel="noreferrer" className="block w-full self-start sm:w-40">
                <img src={shotUrl(run.id, shotName(f.screenshot)!)} alt={`Step ${f.step ?? ""} where it was found`} loading="lazy" className="h-24 w-full rounded-lg border border-[#262626] object-cover object-top" />
                {f.step != null && <span className="num mt-1 block text-[11px] text-dim">step {f.step}</span>}
              </a>
            )}
          </li>
        ))}
      </ul>
    </section>
  );
}

function TracePanel({ run, name, evidence, counts }: { run: Run; name: (sku: string) => string; evidence: Evidence[]; counts: (string | 0)[] }) {
  return (
      <section className="glass mt-5 overflow-hidden" aria-labelledby="trace-h">
        <div className="panel-head max-md:flex-col max-md:items-start">
          <div>
            <h3 id="trace-h" className="text-[15px] font-medium tracking-[-0.02em]">
              Purchase trace
            </h3>
            <p className="mt-0.5 text-[13px] text-faint">What happened to the purchase: five records of it, compared field by field.</p>
          </div>
          <div className="flex flex-wrap items-center gap-x-4 gap-y-1.5 text-xs text-dim">
            <span>
              <b className="mr-1 font-medium text-muted-foreground">Unknown</b>the source doesn&apos;t show it
            </span>
            <span>
              <b className="mr-1 font-medium text-muted-foreground">n/a</b>that record never has this field
            </span>
            {counts.length > 0 && <span className="rounded-full border border-[#262626] bg-[#141414] px-2.5 py-0.5 font-medium text-muted-foreground">{counts.join(" · ")}</span>}
          </div>
        </div>
        <div className="relative py-5 md:px-5">
          <TraceTable trace={run.trace} name={name} evidence={evidence} />
        </div>
      </section>
  );
}

export function Results({ run, health, runs, wide }: { run: Run; health: Health; runs: RunSummary[]; wide: boolean }) {
  const card = run.scorecard;
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const score = useCountUp(card?.simple.score ?? 0);
  // The before and after grid shows only when an earlier check of this store exists (the API answers 404 otherwise).
  const cmp = useFetch(() => (card && run.status === "completed" ? fetchCompare(run.id) : Promise.resolve(null)), [run.id, run.status, !!card]);

  // The other shopper path's latest check of this store, when there is one (404 means there is none yet).
  const pathCmp = useFetch(
    () => (run.status === "completed" ? api.comparePath(run.id).catch((e) => (e instanceof ApiError && e.status === 404 ? null : Promise.reject(e))) : Promise.resolve(null)),
    [run.id, run.status],
  );

  const again = async () => {
    setBusy(true);
    setError(null);
    try {
      const { run_id } = await startCheck(run.live ? run.store_url : null, null, false, run.path === "webmcp" ? { store: run.webmcp?.external_demo ? "paypal_showcase" : "demo" } : undefined);
      go(`/run/${run_id}`);
    } catch (e) {
      setError((e as Error).message);
      setBusy(false);
    }
  };

  // Scans the run list (up to 50 rows, with a nested scan for the example pair); cached across count-up frames.
  const { earlier, example } = useMemo(() => {
    const earlier = runs.find((r) => r.id < run.id && sameSeries(run, r) && r.score != null);
    // Visitors can't change the shared demo store, so its before and after comes from the shared example pair.
    const scored = (r: RunSummary) => r.example && !r.live && r.score != null;
    const example =
      !run.live && !earlier && !health.demo_admin_open
        ? runs.find((r) => scored(r) && runs.some((p) => scored(p) && p.id < r.id))
        : undefined;
    return { earlier, example };
  }, [run, runs, health.demo_admin_open]);

  // Trace cells hold SKUs. The only name the run carries is its target product, which is the SKU the agent wanted.
  const wantedSku = run.trace.stages[0].cells.product;
  const name = (sku: string) => (wantedSku.kind === "known" && String(wantedSku.value) === sku && run.target_product ? run.target_product : sku);

  const first = run.trace.first_mismatch;
  const stage = first && run.trace.stages.find((s) => s.key === first.stage);
  const evidence: Evidence[] = [];
  if (stage?.evidence.screenshot) evidence.push({ label: `${HEAD[stage.key]}, step ${stage.evidence.step}`, href: shotUrl(run.id, stage.evidence.screenshot) });
  const cost = card?.fixes.filter((f) => f.status === "failed").length ?? 0;
  const counts = [run.trace.counts.mismatch && `${run.trace.counts.mismatch} ${run.trace.counts.mismatch === 1 ? "mismatch" : "mismatches"}`, run.trace.counts.unknown && `${run.trace.counts.unknown} unknown`].filter(Boolean);

  return (
    <div>
      <p className="flex items-center gap-2 text-[13px] text-faint">
        <a href="#/checks" className="text-faint no-underline hover:text-foreground">
          My checks
        </a>
        <ChevronRight className="size-3 text-dim" aria-hidden />
        <span className="text-foreground">Check {run.id}</span>
      </p>
      <header className="mt-3.5 flex flex-col gap-4 md:flex-row md:items-end md:justify-between md:gap-6">
        <div className="min-w-0">
          <h1 className="text-2xl leading-[1.15] font-medium tracking-[-0.035em] text-balance sm:text-[30px]">{verdict(run)}</h1>
          <div className="mt-2.5 flex flex-wrap items-center gap-x-2.5 gap-y-1.5 text-[13.5px] text-faint">
            <Store className="size-3.5 text-dim" aria-hidden />
            <span>{storeName(run)}</span>
            {run.target_product && <span className="max-sm:hidden">· {run.target_product}</span>}
            <span className="max-sm:hidden">· {checkedAt(run.started_at)}</span>
            <ModeLabels run={run} health={health} />
          </div>
        </div>
        <div className="flex gap-2 max-md:w-full [&>*]:max-md:flex-1">
          {card && <DeveloperDialog runId={run.id} className="h-9 rounded-lg bg-card text-[13.5px]" />}
          <Button onClick={again} disabled={busy} className="shine h-9 rounded-lg px-3.5 text-[13.5px]">
            <RotateCw aria-hidden />
            {busy ? "Starting…" : "Check again"}
          </Button>
        </div>
      </header>
      {error && (
        <p role="alert" className="mt-4 text-sm text-bad">
          {error}
        </p>
      )}

      {run.path === "webmcp" ? (
        <>
          <div className="mt-6">
            <WebMCPStrip run={run} />
          </div>
          <div className="mt-5">
            <TracePanel run={run} name={name} evidence={evidence} counts={counts} />
          </div>
          <WebMCPPanels run={run} />
          {pathCmp.data && <PathCompareTable data={pathCmp.data} className="mt-5" />}
        </>
      ) : card ? (
        <>
          <div className="mt-6">
            <Strip run={run} score={card.simple.score} cost={cost} />
          </div>

          <TracePanel run={run} name={name} evidence={evidence} counts={counts} />

          <div className="mt-5 grid items-start gap-5 lg:grid-cols-[1.15fr_0.85fr]">
            <ReadinessPanel run={run} card={card} score={score} showAll={wide} />
            <MoneyPanel run={run} />
          </div>
        </>
      ) : (
        <section className="glass mt-6 p-6">
          <StatusLine level="unknown" text="We couldn't check your store this time" />
          <p className="mt-2 text-muted-foreground">Something went wrong on our side. Please try again.</p>
        </section>
      )}

      <PathStrip run={run} />
      <SafetyPanel run={run} />

      {card && cmp.data && <CompareGrid data={cmp.data} className="mt-5" />}
      {run.path !== "webmcp" && pathCmp.data && <PathCompareTable data={pathCmp.data} className="mt-5" />}

      {card && (
        <section className="mt-10" aria-labelledby="fix-first">
          <div>
            <div>
              {card.simple.top_fixes.length > 0 ? (
                <>
                  <h2 id="fix-first" className="border-b pb-3 text-xl font-medium tracking-[-0.02em]">
                    What to fix first
                  </h2>
                  <ol>
                    {card.simple.top_fixes.map((f, i) => (
                      <FixItem key={f.check} fix={f} n={i + 1} />
                    ))}
                  </ol>
                  {card.simple.more_fixes > 0 && (
                    <p className="border-t py-4 text-sm text-muted-foreground">
                      {wide ? (
                        <a href={`#/run/${run.id}/advanced`} className="font-medium text-foreground underline decoration-[#444] underline-offset-4 hover:decoration-foreground">
                          {card.simple.more_fixes} more {card.simple.more_fixes === 1 ? "fix" : "fixes"} in the Advanced view
                        </a>
                      ) : (
                        <>
                          {card.simple.more_fixes} more {card.simple.more_fixes === 1 ? "fix is" : "fixes are"} in the report for your developer.
                        </>
                      )}
                    </p>
                  )}
                </>
              ) : (
                card.possible > 0 && (
                  <div>
                    <h2 id="fix-first" className="border-b pb-3 text-xl font-medium tracking-[-0.02em]">
                      What to fix first
                    </h2>
                    <p className="mt-4 text-base">
                      {run.trace.first_mismatch
                        ? "The shopper got through your store and nothing cost readiness points, but your store's records disagree about the purchase. The fix is in the purchase trace above."
                        : "No readiness checks failed. The shopper found the product and got as far as this check went."}
                    </p>
                  </div>
                )
              )}
              <div className="mt-6 flex flex-col items-start gap-1 text-sm">
                {earlier && (
                  <button type="button" onClick={() => go(`/run/${run.id}/compare`)} className="inline-flex min-h-11 items-center gap-1.5 font-medium underline decoration-[#444] underline-offset-4 hover:decoration-foreground">
                    See before and after
                    <ArrowRight className="size-4" aria-hidden />
                  </button>
                )}
                {example && (
                  <button type="button" onClick={() => go(`/run/${example.id}/compare`)} className="inline-flex min-h-11 items-center gap-1.5 font-medium underline decoration-[#444] underline-offset-4 hover:decoration-foreground">
                    See an example before and after on the demo store
                    <ArrowRight className="size-4" aria-hidden />
                  </button>
                )}
                {!run.live && health.demo_admin_open && (
                  <a href="/store/admin" target="_blank" rel="noreferrer" className="inline-flex min-h-11 items-center text-muted-foreground">
                    Fix the demo store (opens its settings)
                  </a>
                )}
              </div>
            </div>
          </div>
          <ProductFeedLine run={run} className="mt-8" />
          <PayPalReadiness run={run} className="mt-8" />
        </section>
      )}
    </div>
  );
}
