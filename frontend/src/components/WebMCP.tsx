import { Check, Minus, X } from "lucide-react";

import { Tag } from "@/components/bits";
import type { PathCompare, PathSide, Run, ToolCheck } from "@/lib/api";
import { cn } from "@/lib/utils";

// WebMCP checks: the shopper uses the store's own tools instead of its web pages. Everything here is read from the
// run's recorded data; the checklist and the comparison are computed by code (backend/app/webmcp), never by the model.

const CHECK_MARK = {
  pass: { icon: Check, text: "Pass" },
  fail: { icon: X, text: "Fail" },
  not_tested: { icon: Minus, text: "Not tested" },
} as const;

const seconds = (run: Run) => (run.finished_at ? Math.round((Date.parse(run.finished_at) - Date.parse(run.started_at)) / 1000) : null);

export function WebMCPStrip({ run }: { run: Run }) {
  const report = run.webmcp;
  const checks = report?.tool_checks ?? [];
  const passed = checks.filter((c) => c.status === "pass").length;
  const done = report?.completion;
  const cell = "relative px-5 py-[18px] [&_small]:block [&_small]:text-xs [&_small]:text-faint [&_b]:mt-1.5 [&_b]:block [&_b]:text-lg [&_b]:font-medium [&_b]:tracking-[-0.02em] [&_span.sub]:mt-[3px] [&_span.sub]:block [&_span.sub]:text-[12.5px] [&_span.sub]:text-[#8a8a8a]";
  const secs = seconds(run);
  return (
    <div className="glass grid grid-cols-2 lg:grid-cols-4" role="group" aria-label="Summary">
      <div className={cell}>
        <small>Purchase</small>
        <b>{run.outcome === "purchased" ? "Paid" : run.outcome === "blocked" ? "Payment failed" : run.outcome === "error" ? "Didn't finish" : "Stopped before paying"}</b>
        <span className="sub">{run.trace.first_mismatch ? "The store's records disagree" : run.trace.counts.unknown ? `${run.trace.counts.unknown} unknown` : "No mismatch found"}</span>
      </div>
      <div className={cn(cell, "border-l")}>
        <small>Money</small>
        <b className="num">{done?.amount ? `${Number(done.amount.value).toFixed(2)} ${done.amount.currency_code} captured` : "Nothing captured"}</b>
        <span className="sub">{report?.external_demo ? "From the tool responses" : "From PayPal's capture"}</span>
      </div>
      <div className={cn(cell, "border-t border-l-0 lg:border-t-0 lg:border-l")}>
        <small>Tool checks</small>
        <b>
          {passed} <span className="text-sm text-dim">/ {checks.length || 8}</span>
        </b>
        <span className="sub">A checklist, not a score</span>
      </div>
      <div className={cn(cell, "border-t border-l lg:border-t-0")}>
        <small>Shopper</small>
        <b>{report?.tool_calls.length ?? 0} tool calls</b>
        <span className="sub">{secs != null ? `${secs} s` : "Still running"}</span>
      </div>
    </div>
  );
}

function ToolChecks({ checks }: { checks: ToolCheck[] }) {
  return (
    <ul>
      {checks.map((c) => {
        const mark = CHECK_MARK[c.status];
        return (
          <li key={c.key} className="grid grid-cols-[auto_1fr] items-start gap-3 border-b px-5 py-3 last:border-b-0">
            <span className="mt-0.5 inline-flex min-w-[88px] items-center gap-1.5 rounded-full border border-[#262626] bg-[#141414] px-2.5 py-0.5 text-xs font-medium text-muted-foreground">
              <mark.icon className="size-3" aria-hidden />
              {mark.text}
            </span>
            <div className="min-w-0">
              <b className="block text-[13.5px] font-medium">{c.label}</b>
              <span className="mt-px block text-[12.5px] break-words text-[#8a8a8a]">{c.evidence}</span>
            </div>
          </li>
        );
      })}
    </ul>
  );
}

export function WebMCPPanels({ run }: { run: Run }) {
  const report = run.webmcp;
  if (!report) return null;
  const found = report.discovery;
  const hand = report.handoff;
  const checks = report.tool_checks ?? [];
  const calls = run.steps;
  return (
    <>
      {report.external_demo && report.label && (
        <p role="note" className="glass mt-5 px-5 py-3.5 text-[13.5px] text-muted-foreground">
          {report.label}
        </p>
      )}
      <section className="glass mt-5 overflow-hidden" aria-labelledby="mcp-tools-h">
        <div className="panel-head max-md:flex-col max-md:items-start">
          <div>
            <h3 id="mcp-tools-h" className="text-[15px] font-medium tracking-[-0.02em]">
              WebMCP tools the page offered
            </h3>
            <p className="mt-0.5 text-[13px] text-faint">{found?.source ?? "No tool API was found on the page."}</p>
          </div>
          <div className="flex flex-wrap gap-2">
            <Tag>PayPal v6 SDK script {found?.paypal_sdk_v6 ? "on the page" : "not found"}</Tag>
            <Tag>WebMCP script {found?.webmcp_script ? "on the page" : "not found"}</Tag>
          </div>
        </div>
        {found && found.tools.length > 0 ? (
          <ul>
            {found.tools.map((t) => (
              <li key={t.name} className="border-b px-5 py-3 last:border-b-0">
                <p className="flex flex-wrap items-center gap-2">
                  <code className="num text-[13px]">{t.name}</code>
                  <Tag>{t.read_only ? "Read-only" : "Can change things"}</Tag>
                </p>
                <p className="mt-1 text-[12.5px] text-[#8a8a8a]">{t.description}</p>
              </li>
            ))}
          </ul>
        ) : (
          <p className="px-5 py-4 text-[13.5px] text-muted-foreground">The shopper had no tools to use on this page.</p>
        )}
      </section>

      <section className="glass mt-5 overflow-hidden" aria-labelledby="mcp-calls-h">
        <div className="panel-head">
          <div>
            <h3 id="mcp-calls-h" className="text-[15px] font-medium tracking-[-0.02em]">
              Tool calls
            </h3>
            <p className="mt-0.5 text-[13px] text-faint">
              {report.tool_calls.length} tool calls in {report.llm_turns} model turns. The PayPal approval is done by the system, never by the model.
            </p>
          </div>
        </div>
        <ol>
          {calls.map((s) => (
            <li key={s.idx} className="grid grid-cols-[2rem_minmax(0,1fr)_auto] items-start gap-x-3 border-b px-5 py-3 last:border-b-0">
              <span className="num text-[12px] text-dim">{s.idx + 1}</span>
              <div className="min-w-0">
                <p className="flex flex-wrap items-center gap-2">
                  <code className="num text-[13px]">{s.tool}</code>
                  <Tag>{s.ok ? "Worked" : "Failed"}</Tag>
                  {s.tool === "paypal_buyer_approval" && <Tag>System step</Tag>}
                </p>
                <p className="mt-1 line-clamp-3 text-[12.5px] break-words text-[#8a8a8a]">{s.observation}</p>
              </div>
              <span className="num text-[11px] text-dim">{s.duration_ms != null ? `${s.duration_ms} ms` : ""}</span>
            </li>
          ))}
        </ol>
      </section>

      <section className="glass mt-5 overflow-hidden" aria-labelledby="mcp-price-h">
        <div className="panel-head">
          <div>
            <h3 id="mcp-price-h" className="text-[15px] font-medium tracking-[-0.02em]">
              Price in each tool result
            </h3>
            <p className="mt-0.5 text-[13px] text-faint">
              Unit price quoted for the product bought
              {report.price_consistency.quantity > 1 ? `, totals divided by ${report.price_consistency.quantity}` : ""}.{" "}
              {report.price_consistency.consistent == null ? "Not enough readable prices to compare." : report.price_consistency.consistent ? "They agree." : "They do not agree."}
            </p>
          </div>
        </div>
        <dl className="grid gap-x-6 gap-y-3 px-5 py-4 text-[13.5px] sm:grid-cols-2 lg:grid-cols-4">
          {(["search", "product", "checkout", "capture"] as const).map((k) => (
            <div key={k}>
              <dt className="text-xs text-faint">{{ search: "searchProducts", product: "getProduct", checkout: "initiateCheckout", capture: "completeCheckout" }[k]}</dt>
              <dd className="num mt-1">{report.price_consistency.unit_prices[k] ?? "unknown"}</dd>
            </div>
          ))}
        </dl>
      </section>

      <section className="glass mt-5 overflow-hidden" aria-labelledby="mcp-hand-h">
        <div className="panel-head">
          <div>
            <h3 id="mcp-hand-h" className="text-[15px] font-medium tracking-[-0.02em]">
              Hand-off to PayPal
            </h3>
            <p className="mt-0.5 text-[13px] text-faint">The buyer approves every payment in PayPal. The shopper never holds sign-in details.</p>
          </div>
        </div>
        {hand ? (
          <dl className="grid gap-x-6 gap-y-3 px-5 py-4 text-[13.5px] sm:grid-cols-2 lg:grid-cols-4">
            <div>
              <dt className="text-xs text-faint">Approval window</dt>
              <dd className="num mt-1 break-all">{hand.approval_url_host ?? "unknown"}</dd>
            </div>
            <div>
              <dt className="text-xs text-faint">Cart</dt>
              <dd className="num mt-1">{hand.cart_id ?? "unknown"}</dd>
            </div>
            <div>
              <dt className="text-xs text-faint">Approved by</dt>
              <dd className="mt-1">{hand.approved ? (hand.approved_by === "human" ? "A person (PayPal's extra check)" : "The sandbox buyer, signed in by the system") : "Not approved"}</dd>
            </div>
            <div>
              <dt className="text-xs text-faint">Outcome</dt>
              <dd className="mt-1">{hand.problem ?? "Approved, then completed"}</dd>
            </div>
          </dl>
        ) : (
          <p className="px-5 py-4 text-[13.5px] text-muted-foreground">Checkout was never started, so PayPal was not reached.</p>
        )}
      </section>

      {checks.length > 0 && (
        <section className="glass mt-5 overflow-hidden" aria-labelledby="mcp-checks-h">
          <div className="panel-head">
            <div>
              <h3 id="mcp-checks-h" className="text-[15px] font-medium tracking-[-0.02em]">
                Tool checks
              </h3>
              <p className="mt-0.5 text-[13px] text-faint">What the tools did, checked by code. This is a checklist: it does not change any score.</p>
            </div>
          </div>
          <ToolChecks checks={checks} />
        </section>
      )}
    </>
  );
}

const PURCHASE = { purchased: "Bought", blocked: "Payment failed", gave_up: "Stopped before paying", error: "Didn't finish" } as Record<string, string>;

function Row({ label, browser, webmcp }: { label: string; browser: string; webmcp: string }) {
  return (
    <tr className="border-b last:border-b-0">
      <th scope="row" className="py-2.5 pr-4 text-left text-[13px] font-normal text-faint">
        {label}
      </th>
      <td className="py-2.5 pr-4 text-[13.5px] break-words">{browser}</td>
      <td className="py-2.5 text-[13.5px] break-words">{webmcp}</td>
    </tr>
  );
}

const calls = (s: PathSide) => `${s.agent_steps} ${s.path === "webmcp" ? "tool calls" : "steps"}`;
const mismatch = (s: PathSide) => (s.final.first_mismatch ? `${s.final.first_mismatch.stage.replace("_", " ")}: ${s.final.first_mismatch.actual}` : "None");
const money = (s: PathSide) => (s.price.captured ? `${s.price.captured}${s.price.catalog ? ` (catalog ${s.price.catalog})` : ""}` : "Nothing captured");

// Browser agent vs WebMCP tools on the same store: the verdict sentence is computed by code, the rows are recorded facts.
export function PathCompareTable({ data, className }: { data: PathCompare; className?: string }) {
  const { browser: b, webmcp: w } = data;
  return (
    <section className={cn("glass overflow-hidden", className)} aria-labelledby="path-compare-h">
      <div className="panel-head max-md:flex-col max-md:items-start">
        <div>
          <h3 id="path-compare-h" className="text-[15px] font-medium tracking-[-0.02em]">
            Browser vs WebMCP
          </h3>
          <p className="mt-0.5 text-[13px] text-faint">
            Checks {b.run_id} and {w.run_id}, same store.
          </p>
        </div>
      </div>
      <p className="px-5 pt-4 text-[15px]">{data.verdict}</p>
      {data.warnings.map((m) => (
        <p key={m} className="px-5 pt-2 text-[13px] text-faint">
          {m}
        </p>
      ))}
      <div className="overflow-x-auto px-5 pt-2 pb-4">
        <table className="w-full min-w-[520px]">
          <thead>
            <tr className="border-b text-left text-xs text-faint">
              <th scope="col" className="py-2 pr-4 font-normal">
                <span className="sr-only">Measure</span>
              </th>
              <th scope="col" className="py-2 pr-4 font-medium">
                Browser agent
              </th>
              <th scope="col" className="py-2 font-medium">
                WebMCP tools
              </th>
            </tr>
          </thead>
          <tbody>
            <Row label="Outcome" browser={PURCHASE[b.outcome ?? ""] ?? "Unknown"} webmcp={PURCHASE[w.outcome ?? ""] ?? "Unknown"} />
            <Row label="Agent actions" browser={calls(b)} webmcp={calls(w)} />
            <Row label="Model turns" browser={b.llm_turns != null ? String(b.llm_turns) : "Not recorded"} webmcp={w.llm_turns != null ? String(w.llm_turns) : "Not recorded"} />
            <Row label="Time" browser={b.duration_s != null ? `${b.duration_s} s` : "Unknown"} webmcp={w.duration_s != null ? `${w.duration_s} s` : "Unknown"} />
            <Row label="Bought" browser={b.product.bought ?? "Nothing"} webmcp={w.product.bought ?? "Nothing"} />
            <Row label="Amount captured" browser={money(b)} webmcp={money(w)} />
            <Row label="PayPal hand-off" browser={b.handoff} webmcp={w.handoff} />
            <Row label="Store order" browser={b.final.store_order_status ?? "Unknown"} webmcp={w.final.store_order_status ?? "Unknown"} />
            <Row label="ID links that match" browser={`${b.final.links_ok} of ${b.final.links_total}`} webmcp={`${w.final.links_ok} of ${w.final.links_total}`} />
            <Row label="First mismatch" browser={mismatch(b)} webmcp={mismatch(w)} />
            <Row label="Readiness score" browser={b.score != null ? `${b.score} / 100` : "Not scored"} webmcp="Not scored (rates web pages)" />
            <Row label="Tool checks passed" browser="Not applicable" webmcp={w.tool_checks ? `${w.tool_checks.filter((c) => c.status === "pass").length} of ${w.tool_checks.length}` : "Not recorded"} />
          </tbody>
        </table>
      </div>
    </section>
  );
}
