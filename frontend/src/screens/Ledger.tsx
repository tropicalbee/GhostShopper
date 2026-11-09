import { AllCommunityModule, ModuleRegistry, type ColDef, type GridApi } from "ag-grid-community";
import { AgGridReact } from "ag-grid-react";
import { Download, TriangleAlert } from "lucide-react";
import { useMemo, useRef, useState } from "react";

import { theme } from "@/components/FailuresGrid";
import { Panel } from "@/components/bits";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { useFetch } from "@/lib/hooks";
import {
  fetchLedger,
  matchesPreset,
  OUTCOME_LABEL,
  PAYPAL_STATUS,
  REPORTED_LABEL,
  type LedgerOutcome,
  type LedgerPreset,
  type LedgerRow,
  type PayPalReported,
} from "@/lib/ledger";
import { cn } from "@/lib/utils";

ModuleRegistry.registerModules([AllCommunityModule]);

// A pinned totals row is a LedgerRow-shaped object with a flag, so the same column definitions fill it.
type GridRow = LedgerRow & { totals?: boolean };

const STAGE: Record<string, string> = { discover: "Find", details: "Details", checkout: "Checkout", payment: "Payment", outcome: "Finish" };
const PRESETS: { key: LedgerPreset; label: string }[] = [
  { key: "all", label: "All" },
  { key: "lost", label: "Lost sales" },
  { key: "agent", label: "Agent only" },
  { key: "unmatched", label: "Not matched in PayPal" },
];

const OUTCOME_CLASS: Record<LedgerOutcome, string> = {
  captured: "border-good/40 text-good",
  refunded: "border-line text-muted-foreground",
  lost: "border-bad/40 bg-bad-soft/40 text-bad",
  at_risk: "border-warn/40 text-warn",
};
const REPORTED_CLASS: Record<PayPalReported, string> = {
  matched: "border-good/40 text-good",
  pending: "border-warn/40 text-warn",
  mismatch: "border-bad/40 bg-bad-soft/40 text-bad",
  not_checked: "border-line text-muted-foreground",
};

function Pill({ className, children, title }: { className: string; children: string; title?: string }) {
  return (
    <span title={title} className={cn("inline-flex items-center border px-2 py-0.5 text-xs font-medium leading-snug", className)}>
      {children}
    </span>
  );
}

const usd = (v: string | null | undefined) => (v == null ? "" : `$${v}`);
const fee = (v: string | null | undefined) => (v == null ? "" : `$${v.replace("-", "")}`);
const when = (iso: string | null) =>
  iso ? new Date(iso).toLocaleString(undefined, { day: "numeric", month: "short", hour: "numeric", minute: "2-digit" }) : "";

function columns(lost: string): ColDef<GridRow>[] {
  const money = (field: keyof LedgerRow, format = usd): ColDef<GridRow> => ({
    field,
    type: "rightAligned",
    width: 112,
    cellClass: "num",
    valueFormatter: (p) => format(p.value),
    comparator: (a, b) => Number(a ?? -Infinity) - Number(b ?? -Infinity),
  });
  return [
    {
      headerName: "Time",
      field: "time",
      width: 150,
      sort: "desc",
      // The pinned row reads "Lost to AI shoppers: $X" across the first five columns.
      colSpan: (p) => (p.node?.rowPinned ? 5 : 1),
      valueFormatter: (p) => (p.data?.totals ? `Lost to AI shoppers: ${usd(lost)}` : when(p.value)),
      cellClass: (p) => (p.data?.totals ? "font-semibold" : ""),
    },
    { headerName: "Source", field: "source", width: 96, valueFormatter: (p) => (p.value === "agent" ? "AI agent" : "Human") },
    {
      headerName: "Store state",
      field: "store_state",
      minWidth: 170,
      flex: 1,
      valueFormatter: (p) => (p.value == null ? "Unknown" : p.value.length ? p.value.join(", ") : "No flaws"),
      tooltipValueGetter: (p) => (p.value?.length ? p.value.join(", ") : undefined),
    },
    {
      headerName: "Outcome",
      field: "outcome",
      width: 124,
      cellRenderer: (p: { value?: LedgerOutcome; data?: GridRow }) =>
        p.value && !p.data?.totals ? <Pill className={OUTCOME_CLASS[p.value]}>{OUTCOME_LABEL[p.value]}</Pill> : null,
    },
    { headerName: "Stopped at", field: "stopped_at", width: 110, valueFormatter: (p) => STAGE[p.value ?? ""] ?? "" },
    money("amount_at_stake", (v) => usd(v)),
    money("gross"),
    { ...money("fee", fee), headerName: "PayPal fee" },
    money("net"),
    money("refund"),
    {
      headerName: "PayPal status",
      field: "paypal_reported",
      width: 214,
      cellRenderer: (p: { value?: PayPalReported; data?: GridRow }) =>
        p.value && p.data && !p.data.totals && p.data.capture_id ? (
          <Pill className={REPORTED_CLASS[p.value]} title={p.data.paypal_status ? `PayPal says: ${PAYPAL_STATUS[p.data.paypal_status] ?? p.data.paypal_status}` : undefined}>
            {p.data.paypal_mode === "mock" ? `${REPORTED_LABEL[p.value]} (practice mode)` : REPORTED_LABEL[p.value]}
          </Pill>
        ) : null,
    },
    { headerName: "PayPal transaction id", field: "capture_id", minWidth: 190, flex: 1, cellClass: "num" },
  ];
}

export function Ledger() {
  const ledger = useFetch(fetchLedger, []);
  const [preset, setPreset] = useState<LedgerPreset>("all");
  const [quick, setQuick] = useState("");
  const api = useRef<GridApi<GridRow> | null>(null);

  const data = ledger.data;
  const cols = useMemo(() => columns(data?.totals.lost ?? "0.00"), [data?.totals.lost]);
  const pinned = useMemo<GridRow[]>(
    () =>
      data
        ? [
            {
              totals: true,
              time: null, source: "agent", run_id: null, store_state: null, outcome: "captured", stopped_at: null,
              amount_at_stake: data.totals.lost, order_id: null, capture_id: null,
              gross: data.totals.captured_gross, fee: data.totals.fees, net: data.totals.net,
              refund: data.totals.refunded, currency: data.totals.currency, paypal_mode: "", paypal_reported: "not_checked", paypal_status: null,
            },
          ]
        : [],
    [data],
  );

  const choose = (key: LedgerPreset) => {
    setPreset(key);
    api.current?.onFilterChanged(); // re-runs the external filter below
  };

  if (ledger.error && !data)
    return (
      <Panel className="mx-auto mt-16 max-w-md py-10 text-center">
        <p className="text-lg font-medium">The sales ledger isn't available</p>
        <p className="mt-2 text-sm text-muted-foreground">{ledger.error}</p>
        <Button className="mt-6 h-11" onClick={ledger.retry}>
          Try again
        </Button>
      </Panel>
    );

  return (
    <div className="pt-10">
      <h1 className="text-2xl font-semibold tracking-[-0.01em]">Agent sales ledger</h1>
      <p className="mt-2 text-muted-foreground">Every AI shopper attempt, checked against PayPal.</p>

      {data?.paypal_error && (
        <div role="alert" className="mt-5 flex items-start gap-3 border border-warn/40 p-4 text-sm">
          <TriangleAlert className="mt-0.5 size-4 shrink-0 text-warn" aria-hidden />
          <p>
            <span className="font-medium">PayPal could not be checked. </span>
            {data.paypal_error} The rows below come from our own records.
          </p>
        </div>
      )}

      <div className="mt-6 flex flex-wrap items-center gap-2">
        <Input
          type="search"
          aria-label="Search the ledger"
          placeholder="Search"
          value={quick}
          onChange={(e) => setQuick(e.target.value)}
          className="h-10 w-56 max-w-full"
        />
        <div className="flex flex-wrap gap-2" role="group" aria-label="Filter rows">
          {PRESETS.map((p) => (
            <Button key={p.key} type="button" size="sm" variant={preset === p.key ? "default" : "outline"} aria-pressed={preset === p.key} className="h-10" onClick={() => choose(p.key)}>
              {p.label}
            </Button>
          ))}
        </div>
        <Button
          type="button"
          size="sm"
          variant="outline"
          className="ml-auto h-10"
          disabled={!data?.rows.length}
          onClick={() => api.current?.exportDataAsCsv({ fileName: "agent-sales-ledger.csv" })}
        >
          <Download aria-hidden />
          Export CSV
        </Button>
      </div>

      <div className="mt-4">
        {!data ? (
          <Skeleton className="h-72 w-full" />
        ) : (
          <AgGridReact<GridRow>
            theme={theme}
            rowData={data.rows}
            columnDefs={cols}
            pinnedBottomRowData={pinned}
            domLayout="autoHeight"
            rowHeight={44}
            quickFilterText={quick}
            isExternalFilterPresent={() => preset !== "all"}
            doesExternalFilterPass={(node) => (node.data ? matchesPreset(node.data, preset) : true)}
            onGridReady={(e) => (api.current = e.api)}
            tooltipShowDelay={300}
            getRowId={(p) => `${p.data.order_id ?? "run"}-${p.data.run_id ?? ""}-${p.data.capture_id ?? ""}`}
            defaultColDef={{ sortable: true, resizable: true, suppressMovable: true, filter: true }}
            overlayNoRowsTemplate="No checkout attempts yet. Run a check with checkout on."
          />
        )}
      </div>
      {data?.rows.some((r) => r.paypal_mode === "mock") && (
        <p className="mt-3 text-xs text-muted-foreground">Rows marked (practice mode) were checked against the practice PayPal, not real PayPal reporting.</p>
      )}
      {data?.paypal_window && (
        <p className="mt-3 text-xs text-muted-foreground">
          PayPal Transaction Search covers the last 31 days. New transactions can take up to three hours to appear, so Pending is normal at first.
        </p>
      )}
    </div>
  );
}
