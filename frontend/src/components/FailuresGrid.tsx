import { AllCommunityModule, ModuleRegistry, themeQuartz, type ColDef } from "ag-grid-community";
import { AgGridReact } from "ag-grid-react";

import type { Fix } from "@/lib/api";

ModuleRegistry.registerModules([AllCommunityModule]);

// Quartz, set to the same font, borders and greys as the shadcn cards around it.
const theme = themeQuartz.withParams({
  fontFamily: "inherit",
  fontSize: 13,
  foregroundColor: "oklch(0.145 0 0)",
  backgroundColor: "#ffffff",
  borderColor: "oklch(0.922 0 0)",
  headerBackgroundColor: "oklch(0.985 0 0)",
  headerTextColor: "oklch(0.556 0 0)",
  headerFontWeight: 500,
  rowHoverColor: "oklch(0.97 0 0)",
  wrapperBorder: false,
  wrapperBorderRadius: 0,
  rowBorder: true,
  columnBorder: false,
  spacing: 7,
});

const STAGE: Record<string, string> = { discover: "Find", details: "Details", checkout: "Checkout", payment: "Payment", outcome: "Finish" };

const columns: ColDef<Fix>[] = [
  {
    headerName: "Problem",
    field: "title",
    tooltipField: "title",
    flex: 1.4,
    minWidth: 200,
    cellClass: "font-medium",
  },
  { headerName: "Stage", field: "stage", width: 105, valueFormatter: (p) => STAGE[p.value] ?? p.value },
  { headerName: "Points", field: "points", width: 90, type: "rightAligned", sort: "desc" },
  {
    headerName: "Result",
    field: "status",
    width: 120,
    cellRenderer: (p: { value: Fix["status"] }) =>
      p.value === "failed" ? (
        <span className="font-medium text-bad">Store issue</span>
      ) : (
        <span className="text-muted-foreground">Not tested</span>
      ),
  },
  {
    headerName: "What we saw",
    field: "reason",
    tooltipField: "reason",
    flex: 1.6,
    minWidth: 220,
    cellClass: "text-muted-foreground",
  },
  {
    headerName: "Selector",
    valueGetter: (p) => p.data?.evidence.selector ?? "",
    tooltipValueGetter: (p) => p.value,
    flex: 1,
    minWidth: 160,
    cellClass: "font-mono text-xs",
  },
  {
    headerName: "Technical fix",
    field: "fix",
    tooltipField: "fix",
    flex: 1.8,
    minWidth: 240,
  },
  {
    headerName: "Evidence",
    width: 110,
    sortable: false,
    cellRenderer: (p: { data?: Fix }) =>
      p.data?.evidence.screenshot_url ? (
        <a href={p.data.evidence.screenshot_url} target="_blank" rel="noreferrer" className="underline underline-offset-4">
          Screenshot
        </a>
      ) : null,
  },
];

export function FailuresGrid({ fixes }: { fixes: Fix[] }) {
  return (
    <div className="overflow-hidden rounded-xl border">
      <AgGridReact<Fix>
        theme={theme}
        rowData={fixes}
        columnDefs={columns}
        domLayout="autoHeight"
        rowHeight={44}
        tooltipShowDelay={300}
        defaultColDef={{ sortable: true, resizable: true, suppressMovable: true }}
        overlayNoRowsTemplate="No failures. Every check the store controls passed."
      />
    </div>
  );
}
