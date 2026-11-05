import { ArrowLeft, BarChart3, CreditCard, Gauge, LineChart as LineIcon } from "lucide-react";
import { Area, AreaChart, Bar, BarChart, CartesianGrid, Cell, LabelList, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { hostOf, Label, ModeLabels, Panel, ScoreGauge, StatusPill } from "@/components/bits";
import { FailuresGrid } from "@/components/FailuresGrid";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { api, DEMO_SKU, sameSeries, type Health, type Run, type RunSummary } from "@/lib/api";
import { go, useFetch } from "@/lib/hooks";
import { cn } from "@/lib/utils";

const STAGES = [
  ["discover", "Find"],
  ["details", "Details"],
  ["checkout", "Checkout"],
  ["payment", "Payment"],
  ["outcome", "Finish"],
] as const;

// Diagonal hatching, as in the reference: dark for points earned, light for points missed.
function Hatches() {
  return (
    <defs>
      <pattern id="hatch-dark" width="6" height="6" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
        <rect width="6" height="6" fill="var(--foreground)" />
        <line x1="0" y1="0" x2="0" y2="6" stroke="white" strokeOpacity="0.22" strokeWidth="2" />
      </pattern>
      <pattern id="hatch-light" width="6" height="6" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
        <rect width="6" height="6" fill="var(--muted)" />
        <line x1="0" y1="0" x2="0" y2="6" stroke="var(--border)" strokeWidth="2" />
      </pattern>
    </defs>
  );
}

const axis = { tickLine: false, axisLine: false, tick: { fill: "var(--muted-foreground)", fontSize: 12 } };

function StageBars({ run }: { run: Run }) {
  const card = run.scorecard!;
  const data = STAGES.map(([key, name]) => {
    const earned = card.stages[key] ?? 0;
    const possible = card.stage_possible?.[key] ?? earned;
    return { name, earned, missed: Math.max(0, possible - earned), label: `${earned}/${possible}` };
  });
  return (
    <ResponsiveContainer width="100%" height={220}>
      <BarChart data={data} margin={{ top: 8, right: 0, bottom: 0, left: -24 }} barCategoryGap="18%">
        <Hatches />
        <CartesianGrid vertical={false} stroke="var(--border)" strokeDasharray="4 4" />
        <XAxis dataKey="name" {...axis} />
        <YAxis {...axis} allowDecimals={false} />
        <Bar dataKey="earned" stackId="s" fill="url(#hatch-dark)" radius={[0, 0, 4, 4]} isAnimationActive={false}>
          <LabelList dataKey="label" position="insideBottom" fill="white" fontSize={12} offset={8} />
        </Bar>
        <Bar dataKey="missed" stackId="s" fill="url(#hatch-light)" radius={[4, 4, 0, 0]} isAnimationActive={false} />
      </BarChart>
    </ResponsiveContainer>
  );
}

function ScoreHistory({ run, runs }: { run: Run; runs: RunSummary[] }) {
  const data = runs
    .filter((r) => sameSeries(run, r) && r.score != null && r.id <= run.id)
    .slice(0, 10)
    .reverse()
    .map((r) => ({ name: `#${r.id}`, score: r.score, current: r.id === run.id }));
  if (data.length < 2) {
    return <p className="flex h-[220px] items-center justify-center text-sm text-muted-foreground">Check again after a fix to see the score change here.</p>;
  }
  return (
    <ResponsiveContainer width="100%" height={220}>
      <AreaChart data={data} margin={{ top: 8, right: 8, bottom: 0, left: -24 }}>
        <defs>
          <linearGradient id="area" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="var(--foreground)" stopOpacity={0.12} />
            <stop offset="100%" stopColor="var(--foreground)" stopOpacity={0} />
          </linearGradient>
        </defs>
        <CartesianGrid vertical={false} stroke="var(--border)" strokeDasharray="4 4" />
        <XAxis dataKey="name" {...axis} />
        <YAxis domain={[0, 100]} {...axis} />
        <Tooltip
          cursor={{ stroke: "var(--border)" }}
          contentStyle={{ background: "var(--foreground)", border: 0, borderRadius: 8, color: "white", fontSize: 12 }}
          itemStyle={{ color: "white" }}
          labelFormatter={(l) => `Run ${l}`}
        />
        <Area
          type="monotone"
          dataKey="score"
          name="Score"
          stroke="var(--foreground)"
          strokeWidth={2}
          fill="url(#area)"
          dot={{ r: 3, fill: "var(--card)", stroke: "var(--foreground)" }}
          isAnimationActive={false}
        />
      </AreaChart>
    </ResponsiveContainer>
  );
}

function Dot({ ok }: { ok: boolean | null }) {
  const word = ok == null ? "Not checked" : ok ? "OK" : "Problem";
  return (
    <span className="flex items-center gap-1.5 text-xs text-muted-foreground">
      <span className={cn("size-2 rounded-full", ok == null ? "bg-border" : ok ? "bg-good" : "bg-bad")} aria-hidden />
      {word}
    </span>
  );
}

function PaymentCheck({ run }: { run: Run }) {
  const status = (key: string) => {
    const s = run.checks.find((c) => c.check_key === key)?.status;
    return s === "pass" ? true : s === "fail" ? false : null;
  };
  const o = run.order;
  if (!o) {
    return (
      <p className="mt-4 text-sm text-muted-foreground">
        {run.live ? "We never pay on real stores, so there is no payment to check." : "This run didn't include a payment."}
      </p>
    );
  }
  const rows: [string, string, boolean | null][] = [
    ["Order", o.order_id, status("paypal_button_found")],
    ["Payment captured", o.capture_status ?? "-", status("capture_completed")],
    ["Amount", `${o.gross_amount ?? o.amount} ${o.currency}`, status("payment_verified")],
    ["PayPal fee", o.paypal_fee ? `${o.paypal_fee} ${o.currency}` : "-", status("payment_verified")],
    ["You receive", o.net_amount ? `${o.net_amount} ${o.currency}` : "-", status("payment_verified")],
  ];
  return (
    <dl className="mt-4 divide-y">
      {rows.map(([k, v, ok]) => (
        <div key={k} className="flex items-center justify-between gap-3 py-2.5 text-sm">
          <dt className="text-muted-foreground">{k}</dt>
          <dd className="flex items-center gap-3">
            <span className="font-medium tabular-nums">{v}</span>
            <Dot ok={ok} />
          </dd>
        </div>
      ))}
    </dl>
  );
}

function Steps({ run }: { run: Run }) {
  return (
    <ol className="divide-y rounded-xl border bg-card">
      {run.steps.map((s) => {
        const shot = s.screenshot_path ? `/api/runs/${run.id}/files/${s.screenshot_path.split(/[\\/]/).pop()}` : null;
        return (
          <li key={s.idx} className="flex gap-4 p-4">
            {shot ? (
              <a href={shot} target="_blank" rel="noreferrer" className="shrink-0">
                <img src={shot} alt={`Step ${s.idx} screenshot`} loading="lazy" className="h-20 w-32 rounded-md border object-cover object-top" />
              </a>
            ) : (
              <div className="h-20 w-32 shrink-0 rounded-md border bg-muted" aria-hidden />
            )}
            <div className="min-w-0 text-sm">
              <p className="font-medium">
                <span className="text-muted-foreground tabular-nums">{s.idx}. </span>
                <code className="font-mono">{s.tool}</code>
                {!s.ok && <span className="ml-2 text-bad">failed</span>}
              </p>
              {s.thought && <p className="mt-1">{s.thought}</p>}
              {s.url && <p className="mt-1 truncate text-xs text-muted-foreground">{s.url}</p>}
            </div>
          </li>
        );
      })}
    </ol>
  );
}

function Market({ run }: { run: Run }) {
  const { data, error } = useFetch(() => api.market(DEMO_SKU), []);
  if (run.live) return <Panel className="text-sm text-muted-foreground">The market check runs on the demo store's products only.</Panel>;
  if (error) return <Panel className="text-sm text-bad">{error}</Panel>;
  if (!data) return <Panel className="h-64 animate-pulse" />;
  const rows = [
    { name: "Your price", price: Number(data.our_price), ours: true },
    ...data.comparables.map((c) => ({ name: c.domain, price: Number(c.price), ours: false })),
  ];
  return (
    <Panel>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="font-medium">{data.verdict}</p>
        {data.source === "recorded" && <Badge variant="outline">Sample market data</Badge>}
      </div>
      <ResponsiveContainer width="100%" height={rows.length * 36 + 20}>
        <BarChart data={rows} layout="vertical" margin={{ top: 12, right: 40, bottom: 0, left: 0 }}>
          <Hatches />
          <XAxis type="number" hide />
          <YAxis type="category" dataKey="name" width={170} {...axis} />
          <Bar dataKey="price" radius={4} isAnimationActive={false} barSize={20}>
            {rows.map((r) => (
              <Cell key={r.name} fill={r.ours ? "url(#hatch-dark)" : "url(#hatch-light)"} />
            ))}
            <LabelList dataKey="price" position="right" formatter={(v) => `$${Number(v).toFixed(2)}`} fill="var(--foreground)" fontSize={12} />
          </Bar>
        </BarChart>
      </ResponsiveContainer>
      {data.source_note && <p className="mt-2 text-xs text-muted-foreground">{data.source_note}</p>}
    </Panel>
  );
}

function NotFault({ run }: { run: Run }) {
  const card = run.scorecard!;
  const items = [...card.not_store_fault, ...card.not_checked_live];
  if (!items.length) return <Panel className="text-sm text-muted-foreground">Everything in this run was the store's to control.</Panel>;
  return (
    <Panel>
      <ul className="divide-y">
        {items.map((n) => (
          <li key={n.check} className="py-3">
            <p className="font-medium">
              {n.title} <span className="font-normal text-muted-foreground">({n.points} points, not counted)</span>
            </p>
            <p className="mt-1 text-sm text-muted-foreground">{n.plain}</p>
            {n.reason && <p className="mt-1 text-xs text-muted-foreground">{n.reason}</p>}
          </li>
        ))}
      </ul>
    </Panel>
  );
}

export function Advanced({ run, runs, health }: { run: Run; runs: RunSummary[]; health: Health }) {
  const card = run.scorecard;
  if (!card) return <Panel className="text-center text-muted-foreground">This run has no score to break down.</Panel>;
  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-col gap-1">
          <h1 className="text-2xl font-semibold tracking-tight">
            Run #{run.id} · {run.live ? hostOf(run.store_url) : "Demo store"}
          </h1>
          <ModeLabels run={run} health={health} />
        </div>
        <Button variant="outline" onClick={() => go(`/run/${run.id}`)}>
          <ArrowLeft aria-hidden />
          Simple view
        </Button>
      </div>

      <div className="grid gap-4 lg:grid-cols-12">
        <Panel className="flex flex-col lg:col-span-4">
          <Label icon={Gauge}>Readiness score</Label>
          <div className="mt-6">
            <ScoreGauge score={card.total} size={240} caption={`judged on ${card.possible} of 100 points`} />
          </div>
          <div className="mt-4 flex justify-center">
            <StatusPill level={card.simple.status} text={card.simple.status_text} />
          </div>
          <p className="mt-auto pt-4 text-center text-xs text-muted-foreground">Rules {card.rules_version}. Computed from checks, never by the AI.</p>
        </Panel>
        <Panel className="lg:col-span-8">
          <Label icon={LineIcon}>Score across runs</Label>
          <div className="mt-4">
            <ScoreHistory run={run} runs={runs} />
          </div>
        </Panel>
        <Panel className="lg:col-span-7">
          <Label icon={BarChart3}>Points by stage</Label>
          <div className="mt-4">
            <StageBars run={run} />
          </div>
        </Panel>
        <Panel className="lg:col-span-5">
          <Label icon={CreditCard}>Payment check</Label>
          <PaymentCheck run={run} />
        </Panel>
      </div>

      <Tabs defaultValue="failures" className="mt-2">
        <TabsList>
          <TabsTrigger value="failures">Failures ({card.fixes.filter((f) => f.status === "failed").length})</TabsTrigger>
          <TabsTrigger value="steps">Agent steps ({run.steps.length})</TabsTrigger>
          <TabsTrigger value="market">Market</TabsTrigger>
          <TabsTrigger value="fault">Not the store's fault</TabsTrigger>
        </TabsList>
        <TabsContent value="failures" className="mt-3">
          <FailuresGrid fixes={card.fixes} />
        </TabsContent>
        <TabsContent value="steps" className="mt-3">
          <Steps run={run} />
        </TabsContent>
        <TabsContent value="market" className="mt-3">
          <Market run={run} />
        </TabsContent>
        <TabsContent value="fault" className="mt-3">
          <NotFault run={run} />
        </TabsContent>
      </Tabs>
    </div>
  );
}
