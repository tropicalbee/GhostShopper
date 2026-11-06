import type { ColDef } from "ag-grid-community";
import { AgGridReact } from "ag-grid-react";

import { CELL, theme } from "@/components/FailuresGrid";
import { DownloadLink } from "@/components/ProductFeedLine";
import type { FeedField, Run } from "@/lib/api";
import { cn } from "@/lib/utils";

const STATUS = {
  found: { word: "Found", tone: "text-good" },
  partial: { word: "Partly", tone: "text-warn" },
  missing: { word: "Missing", tone: "text-bad" },
} as const;

const columns: ColDef<FeedField>[] = [
  { headerName: "Column", field: "field", width: 130, cellClass: `${CELL} num` },
  { headerName: "Needed", field: "required", width: 120, cellClass: CELL, valueFormatter: (p) => (p.value ? "Required" : "Recommended") },
  {
    headerName: "Status",
    field: "status",
    width: 100,
    cellClass: CELL,
    cellRenderer: (p: { value: FeedField["status"] }) => <span className={cn("font-medium", STATUS[p.value].tone)}>{STATUS[p.value].word}</span>,
  },
  {
    headerName: "What the shopper read",
    field: "value",
    flex: 1.3,
    minWidth: 180,
    wrapText: true,
    autoHeight: true,
    cellClass: `${CELL} [overflow-wrap:anywhere]`,
    cellRenderer: (p: { data?: FeedField }) =>
      p.data?.value ? (
        <span>
          <span className="num">{p.data.value}</span>
          {p.data.source && <span className="text-muted-foreground"> ({p.data.source})</span>}
        </span>
      ) : (
        <span className="text-muted-foreground">Nothing on the page</span>
      ),
  },
  {
    headerName: "How to fill the gap",
    field: "fix",
    flex: 1.6,
    minWidth: 220,
    wrapText: true,
    autoHeight: true,
    cellClass: `${CELL} text-muted-foreground`,
    valueGetter: (p) => (p.data ? [p.data.note, p.data.fix].filter(Boolean).join(" ") : ""),
  },
];

const NOTE =
  "This is the file you would submit to PayPal's Store Sync or Agent Ready. PayPal has no sandbox for these programs, so GhostShopper does not submit anything. It is built from what the shopper read on your product page, so gaps are gaps in your page.";

// Advanced view: every feed column with what was found and how to fill what is missing.
export function ProductFeed({ run }: { run: Run }) {
  const feed = run.product_feed;
  if (!feed) {
    return (
      <p className="border-t-[1.5px] border-rule py-8 text-muted-foreground">
        {run.status === "running" || run.status === "awaiting_human"
          ? "The feed is built once the shopper has read the product page."
          : "The shopper did not read a product page in this check, or the check is older than this feature. Check the store again to get a feed."}
      </p>
    );
  }
  return (
    <div className="border-t-[1.5px] border-rule pt-5">
      <div className="flex flex-wrap items-center justify-between gap-x-6 gap-y-3">
        <div>
          <p className="font-medium">
            <span className="num">
              {feed.required_found} of {feed.required_total}
            </span>{" "}
            required columns found
          </p>
          <p className="mt-1 max-w-2xl text-sm text-muted-foreground">{NOTE}</p>
        </div>
        <DownloadLink runId={run.id} />
      </div>
      <div className="mt-5">
        <AgGridReact<FeedField>
          theme={theme}
          rowData={feed.fields}
          columnDefs={columns}
          domLayout="autoHeight"
          rowHeight={44}
          onFirstDataRendered={(e) => e.api.resetRowHeights()}
          onGridSizeChanged={(e) => e.api.resetRowHeights()}
          defaultColDef={{ sortable: false, resizable: true, suppressMovable: true }}
        />
      </div>
    </div>
  );
}
