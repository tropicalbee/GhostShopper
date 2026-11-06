import { RotateCw } from "lucide-react";
import { useMemo, useState } from "react";
import { Bar, BarChart, CartesianGrid, Cell, LabelList, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { Label, ScoreFigure, ShopperPath, StatusLine } from "@/components/bits";
import { DeveloperDialog } from "@/components/dialogs";
import { FailuresGrid } from "@/components/FailuresGrid";
import { PayPalReadiness } from "@/components/PayPalReadiness";
import { ProductFeed } from "@/components/ProductFeed";
import { RunHead, ViewSwitch } from "@/components/RunHead";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { RefundTest, refundedOf } from "@/components/RefundTest";
import { api, DEMO_SKU, sameSeries, startCheck, type Health, type Run, type RunSummary } from "@/lib/api";
import { go, useFetch } from "@/lib/hooks";
import { cn } from "@/lib/utils";

const axis = { tickLine: false, axisLine: false, tick: { fill: "var(--muted-foreground)", fontSize: 12, fontFamily: "var(--font-mono)" } };

// The key moments: the first line, every success, the first two problems, any note, and always the last line.
function keyMoments(run: Run) {
  const bad = run.feed.map((l, i) => (l.tone === "bad" ? i : -1)).filter((i) => i >= 0).slice(0, 2);
  const keep = new Set([0, run.feed.length - 1, ...bad]);
  run.feed.forEach((l, i) => (l.tone === "good" || l.tone === "info") && keep.add(i));
  return [...keep].filter((i) => i >= 0).sort((a, b) => a - b).slice(-8).map((i) => run.feed[i]);
}

function WhatTheShopperDid({ run }: { run: Run }) {
  const lines = useMemo(() => keyMoments(run), [run.feed]);
  return (
    <>
      <ol className="mt-3 text-sm">
        {lines.map((l, i) => (
          <li key={i} className="grid grid-cols-[2.5rem_minmax(0,1fr)] border-b py-2.5 last:border-b-0">
            <span className="num text-[13px] text-muted-foreground">{l.step}</span>
            <span className={cn(l.tone === "bad" && "text-bad", l.tone === "info" && "text-muted-foreground")}>{l.text}</span>
          </li>
        ))}
      </ol>
      {run.feed.length > lines.length && <p className="mt-2 text-[13px] text-muted-foreground">Every step is in the Agent steps tab below.</p>}
    </>
  );
}

function PaymentLedger({ run }: { run: Run }) {
  const o = run.order;
  if (!o) {
    return (
      <p className="mt-4 text-sm text-muted-foreground">
        {run.live ? "We never pay on real stores, so there's no payment to check." : "This check didn't include a payment."}
      </p>
    );
  }
  const money = (v: string | null) => (v ? `${v} ${o.currency}` : "Not captured");
  const rows: [string, string, boolean][] = [
    ["Order", o.order_id, true],
    ["Captured", o.capture_status === "COMPLETED" ? "Completed" : (o.capture_status ?? "Not captured"), false],
    ["Charged", money(o.gross_amount ?? o.amount), true],
    ["PayPal fee", o.paypal_fee ? `−${o.paypal_fee} ${o.currency}` : "Not reported", true],
  ];
  return (
    <>
    <dl className="mt-3 text-sm">
      {rows.map(([k, v, mono]) => (
        <div key={k} className="flex justify-between gap-4 border-b py-2.5">
          <dt className="text-muted-foreground">{k}</dt>
          <dd className={cn(mono && "num", "text-right [overflow-wrap:anywhere]")}>{v}</dd>
        </div>
      ))}
      <div className="-mt-px flex justify-between gap-4 border-t-[1.5px] border-rule py-2.5 font-semibold">
        <dt>You receive</dt>
        <dd className="num">{money(o.net_amount)}</dd>
      </div>
    </dl>
    {o.capture_status === "COMPLETED" && run.mine && (
      <RefundTest key={o.order_id} orderId={o.order_id} currency={o.currency} refunded={refundedOf(o)} />
    )}
    </>
  );
}

function Steps({ run }: { run: Run }) {
  return (
    <ol className="border-t-[1.5px] border-rule">
      {run.steps.map((s) => {
        const shot = s.screenshot_path ? `/api/runs/${run.id}/files/${s.screenshot_path.split(/[\\/]/).pop()}` : null;
        return (
          <li key={s.idx} className="grid grid-cols-[2.5rem_8.5rem_minmax(0,1fr)] gap-4 border-b py-4">
            <span className="num text-[13px] text-muted-foreground">{s.idx}</span>
            {shot ? (
              <a href={shot} target="_blank" rel="noreferrer" aria-label={`Open the screenshot of step ${s.idx}`}>
                <img src={shot} alt="" loading="lazy" className="h-20 w-34 border object-cover object-top" />
              </a>
            ) : (
              <span className="hatch h-20 w-34 border" aria-hidden />
            )}
            <div className="min-w-0 text-sm">
              <p>
                <span className="num">{s.tool}</span>
                {!s.ok && <span className="ml-2 text-bad">failed</span>}
              </p>
              {s.thought && <p className="mt-1 text-muted-foreground">{s.thought}</p>}
              {s.url && <p className="num mt-1 truncate text-xs text-muted-foreground">{s.url}</p>}
            </div>
          </li>
        );
      })}
    </ol>
  );
}

function History({ run, runs }: { run: Run; runs: RunSummary[] | null }) {
  const data = useMemo(
    () =>
      (runs ?? [])
        .filter((r) => sameSeries(run, r) && r.score != null && r.id <= run.id)
        .slice(0, 12)
        .reverse()
        .map((r) => ({ name: `#${r.id}`, score: r.score })),
    [run, runs],
  );
  if (!runs) return <div className="hatch h-[17.5rem] border-y-[1.5px] border-t-rule" role="status" aria-busy="true" aria-label="Loading the history" />;
  if (data.length < 2) {
    return <p className="border-t-[1.5px] border-rule py-8 text-muted-foreground">Make your fixes and check again to see the score change here.</p>;
  }
  return (
    <div className="border-t-[1.5px] border-rule pt-6">
      <ResponsiveContainer width="100%" height={260}>
        <LineChart data={data} margin={{ top: 8, right: 16, bottom: 0, left: -20 }}>
          <CartesianGrid vertical={false} stroke="var(--border)" />
          <XAxis dataKey="name" {...axis} />
          <YAxis domain={[0, 100]} ticks={[0, 25, 50, 75, 100]} {...axis} />
          <Tooltip
            cursor={{ stroke: "var(--line)" }}
            contentStyle={{ background: "var(--background)", border: "1px solid var(--border)", borderRadius: 0, fontSize: 13 }}
            labelFormatter={(l) => `Check ${l}`}
          />
          <Line type="linear" dataKey="score" name="Score" stroke="var(--earned)" strokeWidth={2} dot={{ r: 3, fill: "var(--background)", stroke: "var(--earned)", strokeWidth: 2 }} isAnimationActive={false} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

function Market({ run }: { run: Run }) {
  const { data, error } = useFetch(() => (run.live ? Promise.resolve(null) : api.market(DEMO_SKU)), [run.live]);
  if (run.live) return <p className="border-t-[1.5px] border-rule py-8 text-muted-foreground">The market check runs on the demo store's products only.</p>;
  if (error) return <p className="border-t-[1.5px] border-rule py-8 text-bad">{error}</p>;
  if (!data) return <div className="hatch h-64 border-y-[1.5px] border-t-rule" role="status" aria-busy="true" aria-label="Loading the market check" />;
  const rows = [
    { name: "Your price", price: Number(data.our_price), ours: true },
    ...data.comparables.map((c) => ({ name: c.domain, price: Number(c.price), ours: false })),
  ];
  return (
    <div className="border-t-[1.5px] border-rule pt-5">
      <div className="flex flex-wrap items-baseline justify-between gap-3">
        <p className="font-medium">{data.verdict}</p>
        {data.source === "recorded" && <span className="border px-2.5 py-0.5 text-xs">Sample market data</span>}
      </div>
      <ResponsiveContainer width="100%" height={rows.length * 34 + 16}>
        <BarChart data={rows} layout="vertical" margin={{ top: 16, right: 64, bottom: 0, left: 0 }}>
          <XAxis type="number" hide />
          <YAxis type="category" dataKey="name" width={180} {...axis} tick={{ ...axis.tick, fontFamily: "var(--font-sans)", fontSize: 13 }} />
          <Bar dataKey="price" isAnimationActive={false} barSize={14}>
            {rows.map((r) => (
              <Cell key={r.name} fill={r.ours ? "var(--earned)" : "var(--line)"} />
            ))}
            <LabelList dataKey="price" position="right" formatter={(v) => `$${Number(v).toFixed(2)}`} fill="var(--foreground)" fontSize={12} fontFamily="var(--font-mono)" />
          </Bar>
        </BarChart>
      </ResponsiveContainer>
      {data.source_note && <p className="mt-2 text-[13px] text-muted-foreground">{data.source_note}</p>}
    </div>
  );
}

function NotFault({ run }: { run: Run }) {
  const card = run.scorecard!;
  const items = [...card.not_store_fault, ...card.not_checked_live];
  if (!items.length) return <p className="border-t-[1.5px] border-rule py-8 text-muted-foreground">Everything in this check was the store's to control.</p>;
  return (
    <ul className="border-t-[1.5px] border-rule">
      {items.map((n) => (
        <li key={n.check} className="border-b py-4">
          <p className="font-medium">
            {n.title} <span className="font-normal text-muted-foreground">(<span className="num">{n.points}</span> points, not counted)</span>
          </p>
          <p className="mt-1 text-sm text-muted-foreground">{n.plain}</p>
        </li>
      ))}
    </ul>
  );
}

export function Advanced({ run, runs, health }: { run: Run; runs: RunSummary[] | null; health: Health }) {
  const card = run.scorecard;
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  if (!card) return <p className="pt-10 text-muted-foreground">This check has no score to break down.</p>;

  const again = async () => {
    setBusy(true);
    setError(null);
    try {
      const { run_id } = await startCheck(run.live ? run.store_url : null);
      go(`/run/${run_id}`);
    } catch (e) {
      setError((e as Error).message);
      setBusy(false);
    }
  };
  const failed = card.fixes.filter((f) => f.status === "failed").length;
  const verified = run.checks.find((c) => c.check_key === "payment_verified")?.status === "pass";
  const notFault = card.not_store_fault.length + card.not_checked_live.length;

  return (
    <div>
      <RunHead
        run={run}
        health={health}
        actions={
          <>
            <ViewSwitch runId={run.id} advanced />
            <DeveloperDialog runId={run.id} />
            <Button onClick={again} disabled={busy} className="h-10">
              <RotateCw aria-hidden />
              {busy ? "Starting…" : "Check again"}
            </Button>
          </>
        }
      />
      {error && <p role="alert" className="mt-4 text-sm text-bad">{error}</p>}

      <div className="mt-6 grid grid-cols-12 border-t border-l">
        <section className="col-span-12 flex flex-col justify-between gap-6 border-r border-b bg-panel p-6 md:flex-row md:items-end xl:col-span-4 xl:flex-col xl:items-stretch xl:gap-0">
          <div>
            <Label>Readiness score</Label>
            <ScoreFigure score={card.total} className="mt-5 text-[5.5rem]" />
          </div>
          <div className="xl:mt-6">
            <StatusLine level={card.simple.status} text={card.simple.status_text} />
            <p className="mt-1.5 text-[13px] text-muted-foreground">
              Judged on <span className="num">{card.possible}</span> of 100 points the store controls
            </p>
          </div>
        </section>
        <section className="col-span-12 border-r border-b p-6 xl:col-span-8">
          <Label aside={<span><span className="num">{card.total}</span> of 100 points</span>}>The shopper's path</Label>
          <div className="mt-7">
            <ShopperPath card={card} />
          </div>
          <p className="mt-6 flex flex-wrap gap-x-5 gap-y-1 text-[13px] text-muted-foreground">
            <span className="flex items-center gap-1.5"><span className="size-2.5 bg-earned" aria-hidden />Points earned</span>
            <span className="flex items-center gap-1.5"><span className="hatch size-2.5 border" aria-hidden />Points lost</span>
            <span>Each stage is as wide as the points it's worth</span>
          </p>
        </section>
        <section className="col-span-12 border-r border-b p-6 lg:col-span-7">
          <Label aside={<span><span className="num">{run.steps.length}</span> steps</span>}>What the shopper did</Label>
          <WhatTheShopperDid run={run} />
        </section>
        <section className="col-span-12 border-r border-b p-6 lg:col-span-5">
          <Label aside={run.order ? <span className={verified ? "font-medium text-good" : "text-bad"}>{verified ? "Verified" : "Not verified"}</span> : undefined}>Payment check</Label>
          <PaymentLedger run={run} />
        </section>
      </div>

      <Tabs defaultValue="failures" className="mt-12 gap-0">
        <TabsList variant="line" className="h-auto w-full justify-start gap-6 overflow-x-auto border-b p-0">
          {[
            ["failures", "Failures", failed],
            ["steps", "Agent steps", run.steps.length],
            ["paypal", "PayPal readiness", null],
            ["feed", "Product feed", null],
            ["history", "History", null],
            ["market", "Market", null],
            ["fault", "Not the store's fault", notFault],
          ].map(([value, label, count]) => (
            <TabsTrigger key={value as string} value={value as string} className="h-11 flex-none px-0 text-sm after:bottom-[-1px]">
              {label}
              {count !== null && <span className="num text-xs text-muted-foreground">{count}</span>}
            </TabsTrigger>
          ))}
        </TabsList>
        <TabsContent value="failures" className="mt-4">
          <FailuresGrid fixes={card.fixes.filter((f) => f.status === "failed")} />
        </TabsContent>
        <TabsContent value="steps" className="mt-4">
          <Steps run={run} />
        </TabsContent>
        <TabsContent value="paypal" className="mt-4">
          <PayPalReadiness run={run} />
        </TabsContent>
        <TabsContent value="feed" className="mt-4">
          <ProductFeed run={run} />
        </TabsContent>
        <TabsContent value="history" className="mt-4">
          <History run={run} runs={runs} />
        </TabsContent>
        <TabsContent value="market" className="mt-4">
          <Market run={run} />
        </TabsContent>
        <TabsContent value="fault" className="mt-4">
          <NotFault run={run} />
        </TabsContent>
      </Tabs>
      <p className="num mt-8 text-[12px] text-muted-foreground">Rules {card.rules_version}</p>
    </div>
  );
}
