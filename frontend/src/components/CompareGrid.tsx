import type { ColDef, ICellRendererParams } from "ag-grid-community";
import { AgGridReact } from "ag-grid-react";
import { Download } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";

import { CELL, theme } from "@/components/FailuresGrid";
import { Button } from "@/components/ui/button";
import { checkRows, pinnedRows, STAGE_LABEL, STAGE_ORDER, STATUS_LABEL, type CheckStatus, type CompareData, type GridRow } from "@/lib/compare";
import { cn } from "@/lib/utils";

type Preset = "all" | "fixed" | "failing";
const PRESETS: { key: Preset; label: string }[] = [
  { key: "all", label: "All" },
  { key: "fixed", label: "Fixed by the merchant" },
  { key: "failing", label: "Still failing" },
];

const PILL: Record<CheckStatus, string> = {
  pass: "border-good/40 text-good",
  fail: "border-bad/40 text-bad",
  not_tested: "border-line text-muted-foreground",
};

function Pill({ value }: { value: string }) {
  const status = value as CheckStatus;
  return (
    <span className={cn("inline-block border px-2 py-0.5 text-[12px] leading-snug font-medium", PILL[status] ?? PILL.not_tested)}>
      {STATUS_LABEL[status] ?? value}
    </span>
  );
}

// Check rows get a pill; the pinned rows carry plain text (a score, or the money line).
function Outcome({ data, value }: ICellRendererParams<GridRow, string>) {
  if (!data) return null;
  if (data.kind === "check") return <Pill value={value ?? ""} />;
  return <span className={cn(data.kind === "total" ? "num text-base font-semibold" : "font-medium")}>{value}</span>;
}

function Gained({ data, value }: ICellRendererParams<GridRow, number | null>) {
  if (!data || value == null) return null;
  const text = value > 0 ? `+${value}` : String(value);
  return <span className={cn("num font-medium", value > 0 ? "text-good" : value < 0 ? "text-bad" : "text-muted-foreground")}>{text}</span>;
}

const stageIndex = (s: string) => {
  const i = STAGE_ORDER.indexOf(s);
  return i < 0 ? STAGE_ORDER.length : i;
};

const columns: ColDef<GridRow>[] = [
  { headerName: "Check", field: "check", flex: 1.4, minWidth: 170, wrapText: true, autoHeight: true, cellClass: `${CELL} font-medium` },
  {
    headerName: "Stage",
    field: "stage",
    width: 100,
    cellClass: CELL,
    sort: "asc",
    sortIndex: 0,
    comparator: (a: string, b: string) => stageIndex(a) - stageIndex(b),
    valueFormatter: (p) => STAGE_LABEL[p.value] ?? p.value ?? "",
  },
  { headerName: "Points", field: "points", width: 96, type: "rightAligned", sort: "desc", sortIndex: 1, cellClass: `${CELL} num` },
  { headerName: "Before", field: "before", flex: 1, minWidth: 130, wrapText: true, autoHeight: true, sortable: false, cellClass: CELL, cellRenderer: Outcome },
  { headerName: "After", field: "after", flex: 1, minWidth: 130, wrapText: true, autoHeight: true, sortable: false, cellClass: CELL, cellRenderer: Outcome },
  { headerName: "Points gained", field: "gained", width: 130, type: "rightAligned", cellClass: CELL, cellRenderer: Gained },
  {
    headerName: "Fix applied",
    field: "fix",
    flex: 2,
    minWidth: 220,
    wrapText: true,
    autoHeight: true,
    sortable: false,
    cellClass: `${CELL} text-muted-foreground`,
  },
];

// The before and after of one demo run: a row per rubric check, with the score and the money pinned on top.
export function CompareGrid({ data, className }: { data: CompareData; className?: string }) {
  const grid = useRef<AgGridReact<GridRow>>(null);
  const [preset, setPreset] = useState<Preset>("all");
  const rows = useMemo(() => checkRows(data), [data]);
  const pinned = useMemo(() => pinnedRows(data), [data]);

  useEffect(() => {
    grid.current?.api?.onFilterChanged();
  }, [preset]);

  const passes = (row: GridRow) => (preset === "fixed" ? (row.gained ?? 0) > 0 : preset === "failing" ? row.after === "fail" : true);

  return (
    <section className={cn("border bg-card p-6", className)} aria-labelledby="compare-grid" data-testid="compare-grid">
      <p className="text-[13px] text-muted-foreground">
        Check {data.before.run_id} to check {data.after.run_id}
      </p>
      <h2 id="compare-grid" className="mt-1 text-xl font-semibold tracking-[-0.02em]">
        Before and after your fixes
      </h2>
      {data.warnings.map((w) => (
        <p key={w} className="mt-2 text-sm text-muted-foreground">
          {w}
        </p>
      ))}
      <div className="mt-4 flex flex-wrap items-center gap-2" role="group" aria-label="Show checks">
        {PRESETS.map((p) => (
          <Button key={p.key} type="button" size="sm" variant={preset === p.key ? "default" : "outline"} aria-pressed={preset === p.key} onClick={() => setPreset(p.key)}>
            {p.label}
          </Button>
        ))}
        <Button
          type="button"
          size="sm"
          variant="outline"
          className="sm:ml-auto"
          onClick={() => grid.current?.api.exportDataAsCsv({ fileName: `ghostshopper-before-after-${data.after.run_id}.csv` })}
        >
          <Download aria-hidden />
          Export CSV
        </Button>
      </div>
      <div className="mt-3">
        <AgGridReact<GridRow>
          ref={grid}
          theme={theme}
          rowData={rows}
          columnDefs={columns}
          pinnedTopRowData={pinned}
          domLayout="autoHeight"
          rowHeight={44}
          getRowHeight={(p) => (p.node.rowPinned ? 52 : undefined)}
          getRowClass={(p) => (p.node.rowPinned ? "font-semibold bg-panel" : undefined)}
          isExternalFilterPresent={() => preset !== "all"}
          doesExternalFilterPass={(node) => (node.data ? passes(node.data) : true)}
          onFirstDataRendered={(e) => e.api.resetRowHeights()}
          onGridSizeChanged={(e) => e.api.resetRowHeights()}
          defaultColDef={{ sortable: true, resizable: true, suppressMovable: true }}
          overlayNoRowsTemplate="No checks match this filter."
        />
      </div>
    </section>
  );
}
