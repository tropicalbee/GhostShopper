import { Download } from "lucide-react";

import { Label } from "@/components/bits";
import type { Run } from "@/lib/api";
import { cn } from "@/lib/utils";

export function DownloadLink({ runId, className }: { runId: number; className?: string }) {
  return (
    <a
      href={`/api/runs/${runId}/feed.csv`}
      download
      className={cn("inline-flex h-10 items-center gap-2 border px-4 text-sm font-medium hover:bg-panel", className)}
    >
      <Download className="size-4" aria-hidden />
      Download feed.csv
    </a>
  );
}

// Simple view: one plain line and the download.
export function ProductFeedLine({ run, className }: { run: Run; className?: string }) {
  const feed = run.product_feed;
  if (!feed) return null;
  const missing = feed.fields.filter((f) => f.required && f.status !== "found").map((f) => f.field);
  return (
    <section className={cn("border bg-card p-6", className)} aria-labelledby="feed-line">
      <Label className="text-[15px]">
        <span id="feed-line">Product feed</span>
      </Label>
      <p className="mt-3">
        {feed.ready
          ? "Your product page has everything PayPal's product feed needs."
          : `Your product page is missing ${missing.length} of ${feed.required_total} things PayPal's product feed needs: ${missing.join(", ")}.`}
      </p>
      <p className="mt-1 text-[13px] text-muted-foreground">This is the file you would submit, not one we sent. PayPal has no sandbox for it.</p>
      <div className="mt-4 flex flex-wrap items-center gap-x-6 gap-y-2">
        <DownloadLink runId={run.id} />
        {run.scorecard && (
          <a href={`#/run/${run.id}/advanced`} className="hidden text-sm font-medium underline decoration-line underline-offset-4 hover:decoration-foreground md:inline">
            See every column
          </a>
        )}
      </div>
    </section>
  );
}
