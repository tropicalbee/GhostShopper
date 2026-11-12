import { AllCommunityModule, colorSchemeDark, ModuleRegistry, themeQuartz, type ColDef, type GridApi } from "ag-grid-community";
import { AgGridReact } from "ag-grid-react";

import type { Fix } from "@/lib/api";
import { stripLocalOrigin } from "@/lib/utils";

ModuleRegistry.registerModules([AllCommunityModule]);

// Quartz on the black theme: hairline rows, a heading rule, the page's own greys.
export const theme = themeQuartz.withPart(colorSchemeDark).withParams({
  fontFamily: "inherit",
  fontSize: 14,
  foregroundColor: "#ededed",
  backgroundColor: "#050505",
  borderColor: "#1a1a1a",
  headerBackgroundColor: "#0d0d0d",
  headerTextColor: "#a1a1a1",
  headerFontWeight: 500,
  headerFontSize: 13,
  headerRowBorder: { width: 1.5, color: "#2e2e2e" },
  rowHoverColor: "#0f0f0f",
  selectedRowBackgroundColor: "#141414",
  wrapperBorder: false,
  wrapperBorderRadius: 0,
  borderRadius: 0,
  rowBorder: true,
  columnBorder: false,
  headerColumnBorder: false,
  headerColumnResizeHandleColor: "transparent",
  cellHorizontalPadding: 12,
  spacing: 8,
});

// AG Grid sets each cell's line-height to the row height; wrapped text needs normal leading and the same
// top padding in every column so a row's first lines align.
export const CELL = "leading-snug! py-3!";

const STAGE: Record<string, string> = { discover: "Find", details: "Details", checkout: "Checkout", payment: "Payment", outcome: "Finish" };

// Problem, what we saw and the technical fix wrap onto as many lines as they need. Below about 900px
// the technical fix column is hidden (it stays in the developer report) so Evidence stays in view.
// The selector rides in the technical fix's tooltip and in the developer report.
const columns: ColDef<Fix>[] = [
  { headerName: "Problem", field: "title", flex: 1.3, minWidth: 160, wrapText: true, autoHeight: true, cellClass: `${CELL} font-medium`, valueFormatter: (p) => stripLocalOrigin(p.value) },
  { headerName: "Stage", field: "stage", width: 96, cellClass: CELL, valueFormatter: (p) => STAGE[p.value] ?? p.value },
  { headerName: "Points", field: "points", width: 100, type: "rightAligned", sort: "desc", cellClass: `${CELL} num` },
  {
    headerName: "What we saw",
    field: "reason",
    flex: 1.6,
    minWidth: 180,
    wrapText: true,
    autoHeight: true,
    cellClass: `${CELL} text-muted-foreground`,
    // Example checks were recorded against a local server; show the store's own path, not that address.
    valueFormatter: (p) => stripLocalOrigin(p.value),
  },
  {
    headerName: "Technical fix",
    field: "fix",
    flex: 1.8,
    minWidth: 200,
    wrapText: true,
    autoHeight: true,
    cellClass: CELL,
    valueFormatter: (p) => stripLocalOrigin(p.value),
    tooltipValueGetter: (p) => {
      const fix = stripLocalOrigin(p.value);
      return p.data?.evidence.selector ? `${fix}

Selector: ${stripLocalOrigin(p.data.evidence.selector)}` : fix;
    },
  },
  {
    headerName: "Evidence",
    width: 104,
    cellClass: CELL,
    sortable: false,
    cellRenderer: (p: { data?: Fix }) =>
      p.data?.evidence.screenshot_url ? (
        <a href={p.data.evidence.screenshot_url} target="_blank" rel="noreferrer" className="text-foreground underline decoration-line underline-offset-4 hover:decoration-foreground">
          Screenshot
        </a>
      ) : (
        <span className="text-muted-foreground">None</span>
      ),
  },
];

// Row heights are measured once the columns have their real widths, and again whenever the grid resizes.
function fit(api: GridApi<Fix>, width: number) {
  api.setColumnsVisible(["fix"], width >= 900);
  api.resetRowHeights();
}

export function FailuresGrid({ fixes }: { fixes: Fix[] }) {
  return (
    <div>
      <AgGridReact<Fix>
        theme={theme}
        rowData={fixes}
        columnDefs={columns}
        domLayout="autoHeight"
        rowHeight={44}
        onFirstDataRendered={(e) => e.api.resetRowHeights()}
        onGridSizeChanged={(e) => fit(e.api, e.clientWidth)}
        tooltipShowDelay={300}
        defaultColDef={{ sortable: true, resizable: true, suppressMovable: true }}
        overlayNoRowsTemplate="No failures. Every check the store controls passed."
      />
    </div>
  );
}
