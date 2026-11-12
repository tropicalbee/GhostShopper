import { Camera, MoveHorizontal } from "lucide-react";
import type { ReactNode } from "react";

import type { Trace, TraceCell, TraceLink, TraceStage } from "@/lib/api";

type Field = keyof TraceStage["cells"];

const FIELDS: [Field, string][] = [
  ["product", "Product"],
  ["quantity", "Quantity"],
  ["amount", "Amount"],
  ["currency", "Currency"],
  ["status", "Status"],
];

// The column heads are short; the API's own labels are longer sentences.
export const HEAD: Record<TraceStage["key"], string> = {
  agent_wanted: "Agent wanted",
  store_order: "Store order",
  paypal_order: "PayPal order",
  paypal_capture: "PayPal capture",
  store_says: "Store says",
};

export type Evidence = { label: string; href: string };

function Cell({ cell, field, lit, name }: { cell: TraceCell; field: Field; lit: boolean; name: (sku: string) => string }) {
  if (cell.kind === "unknown")
    return (
      <div className="unk">
        <b>Unknown</b>
        <small>{cell.reason}</small>
      </div>
    );
  if (cell.kind === "n/a")
    return (
      <div className="na">
        <b>n/a</b>
        <small>{cell.reason}</small>
      </div>
    );
  if (cell.kind === "not_reached")
    return (
      <div className="nr">
        <b>Not reached</b>
        <small>{cell.reason}</small>
      </div>
    );
  const raw = cell.value === null ? "" : String(cell.value);
  // Statuses arrive as codes ("awaiting_payment"); PayPal's own words (COMPLETED) stay as they are.
  const text = field === "product" ? name(raw) : field === "status" && raw === raw.toLowerCase() ? raw.replace(/_/g, " ").replace(/^./, (c) => c.toUpperCase()) : raw;
  if (field !== "status") return <>{text}</>;
  return (
    <span
      className={
        lit
          ? "inline-flex rounded-full border border-[#9a9a9a] bg-[#0a0a0a] px-2.5 py-0.5 text-xs font-medium [overflow-wrap:normal] break-normal text-white shadow-[0_0_14px_rgba(255,255,255,0.16)]"
          : "inline-flex rounded-full border border-[#262626] bg-[#141414] px-2.5 py-0.5 text-xs font-medium [overflow-wrap:normal] break-normal text-muted-foreground"
      }
    >
      {text}
    </span>
  );
}

function FieldRow({ field, label, trace, name, children }: { field: Field; label: string; trace: Trace; name: (sku: string) => string; children?: ReactNode }) {
  const first = trace.first_mismatch;
  const numeric = field === "quantity" || field === "amount" || field === "currency";
  return (
    <>
      <tr>
        <td>{label}</td>
        {trace.stages.map((s) => {
          const lit = !!first && first.stage === s.key && first.field === field;
          const cls = [numeric ? "num" : "", s.key === "store_says" && !lit ? "col5" : "", lit ? "hit" : ""].filter(Boolean).join(" ");
          return (
            <td key={s.key} className={cls || undefined}>
              <Cell cell={s.cells[field]} field={field} lit={lit} name={name} />
            </td>
          );
        })}
      </tr>
      {children}
    </>
  );
}

const MARK: Record<TraceLink["kind"], string> = {
  ok: "Linked",
  broken: "Broken",
  unknown: "Unknown",
  "n/a": "n/a",
};

// Do the ids point at the same purchase? Quiet evidence under the table; a broken link is the only lit row.
function LinkChecks({ links }: { links?: TraceLink[] }) {
  if (!links || links.length === 0) return null;
  const first = links[0].reason;
  if (links.every((l) => l.kind === "n/a" && l.reason === first))
    return <p className="mx-4 mt-3 text-xs text-faint">Not checked: {first}</p>;
  return (
    <section className="mx-4 mt-4" aria-labelledby="linked-by-id">
      <h3 id="linked-by-id" className="mb-1.5 text-xs font-medium text-muted-foreground">
        Linked by ID
      </h3>
      <ul className="divide-y divide-[#262626] border-y border-[#262626] text-xs">
        {links.map((l) => (
          <li key={l.key} className="flex flex-wrap items-baseline gap-x-3 gap-y-1 py-2">
            <span
              className={
                l.kind === "broken"
                  ? "inline-flex rounded-full border border-[#9a9a9a] bg-[#0a0a0a] px-2.5 py-0.5 font-medium text-white shadow-[0_0_14px_rgba(255,255,255,0.16)]"
                  : "inline-flex rounded-full border border-[#262626] bg-[#141414] px-2.5 py-0.5 font-medium text-muted-foreground"
              }
            >
              {MARK[l.kind]}
            </span>
            <span className="text-foreground">{l.label}</span>
            {l.kind === "broken" ? (
              <span className="break-all text-faint">
                expected {l.expected ?? "nothing"}, got {l.actual ?? "nothing"}
              </span>
            ) : (
              l.kind !== "ok" && l.reason && <span className="text-faint">{l.reason}</span>
            )}
          </li>
        ))}
      </ul>
    </section>
  );
}

// The purchase trace: five records of one purchase, five fields each. Only the first mismatch is lit, and its
// explanation sits directly under the status row (under the table on phones).
export function TraceTable({ trace, name, evidence }: { trace: Trace; name: (sku: string) => string; evidence: Evidence[] }) {
  const first = trace.first_mismatch;
  const detail = first && (
    <>
      <h4>{first.explanation}</h4>
      <p>
        <b>Fix:</b> {first.fix}
      </p>
    </>
  );
  const links = evidence.length > 0 && (
    <div className="ev">
      {evidence.map((e) => (
        <a key={e.href} href={e.href} target="_blank" rel="noreferrer">
          <Camera aria-hidden />
          {e.label}
        </a>
      ))}
    </div>
  );
  // A broken id link has a link key as its field, so its label comes from the links, not the field rows.
  const fieldLabel = first && (FIELDS.find(([k]) => k === first.field)?.[1] ?? trace.links?.find((l) => l.key === first.field)?.label ?? "Linked IDs");
  return (
    <>
      <p className="mb-2.5 flex items-center gap-1.5 px-4 text-xs text-faint md:hidden">
        <MoveHorizontal className="size-3.5" aria-hidden />
        Swipe to see all five records
      </p>
      <div className="tbl fade">
        <div className="tbl-scroll">
          <table className="trace wide">
            <caption className="sr-only">The purchase, as five records compared field by field</caption>
            <colgroup>
              <col className="lbl" />
              {trace.stages.map((s) => (
                <col key={s.key} />
              ))}
            </colgroup>
            <thead>
              <tr>
                <th scope="col">Field</th>
                {trace.stages.map((s) => (
                  <th key={s.key} scope="col" className={s.key === "store_says" ? "col5" : undefined}>
                    <b>{HEAD[s.key]}</b>
                    <small title={s.source ?? undefined}>{s.source ?? "no record"}</small>
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {FIELDS.map(([field, label]) => (
                <FieldRow key={field} field={field} label={label} trace={trace} name={name}>
                  {field === "status" && first && (
                    <tr className="explain">
                      <td colSpan={6}>
                        <div className="explain-grid">
                          <div>
                            <span className="pill-inv">First mismatch</span>
                          </div>
                          <div>{detail}</div>
                          {links}
                        </div>
                      </td>
                    </tr>
                  )}
                </FieldRow>
              ))}
            </tbody>
          </table>
        </div>
      </div>
      {first && (
        <div className="explain-m">
          <span className="pill-inv">First mismatch</span>
          <span className="ml-2 text-xs text-faint">
            {fieldLabel} · {HEAD[first.stage]}
          </span>
          <div className="mt-2.5">{detail}</div>
          {links && <div className="mt-3">{links}</div>}
        </div>
      )}
      <LinkChecks links={trace.links} />
    </>
  );
}
