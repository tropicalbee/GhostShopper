import { Plus, Trash2 } from "lucide-react";
import { useEffect, useState } from "react";

import { checkedAt, StatusLine, storeName } from "@/components/bits";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Skeleton } from "@/components/ui/skeleton";
import { api, type RunSummary } from "@/lib/api";
import { go, useFetch } from "@/lib/hooks";

const PAGE = 20;

const name = (r: RunSummary) => storeName({ live: !!r.live, store_url: r.store_url });
const running = (r: RunSummary) => r.status === "running" || r.status === "awaiting_human";

function level(r: RunSummary) {
  if (r.score == null || !r.score_possible) return "unknown" as const;
  return r.score >= 80 ? ("good" as const) : r.score >= 50 ? ("warn" as const) : ("bad" as const);
}

function state(r: RunSummary) {
  if (running(r)) return "Still checking";
  if (r.status === "error") return "Didn't finish";
  return { good: "Ready for AI shoppers", warn: "Some fixes needed", bad: "AI shoppers will struggle", unknown: "Couldn't check" }[level(r)];
}

export function MyChecks() {
  const health = useFetch(api.health, []);
  // Pages of 20, newest first; "Show more" asks for the runs before the last one loaded.
  const [data, setData] = useState<RunSummary[] | null>(null);
  const [more, setMore] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    api
      .runs({ limit: PAGE })
      .then((page) => {
        if (!alive) return;
        setData(page);
        setMore(page.length === PAGE);
      })
      .catch((e: Error) => alive && setError(e.message));
    return () => {
      alive = false;
    };
  }, []);

  const showMore = async () => {
    if (!data?.length) return;
    setLoadingMore(true);
    setError(null);
    try {
      const page = await api.runs({ limit: PAGE, before: data[data.length - 1].id });
      setData((rows) => [...(rows ?? []), ...page]);
      setMore(page.length === PAGE);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoadingMore(false);
    }
  };

  const [confirm, setConfirm] = useState<RunSummary | null>(null);
  const [busy, setBusy] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);

  const remove = async () => {
    if (!confirm) return;
    setBusy(true);
    setDeleteError(null);
    try {
      await api.deleteRun(confirm.id);
      setData((rows) => rows?.filter((r) => r.id !== confirm.id) ?? null);
      setConfirm(null);
    } catch (e) {
      setDeleteError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const mine = data?.filter((r) => r.mine) ?? [];
  return (
    <div className="pt-8">
      <div className="flex flex-col gap-4 border-b-[1.5px] border-rule pb-5 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <h1 className="text-[1.875rem] leading-tight font-semibold tracking-[-0.03em]">My checks</h1>
          <p className="mt-1 text-muted-foreground">Saved in this browser only. Other people can't see them.</p>
        </div>
        <Button className="h-10 self-start sm:self-auto" onClick={() => go("/")}>
          <Plus aria-hidden />
          New check
        </Button>
      </div>

      {error && <p role="alert" className="mt-4 text-sm text-bad">{error}</p>}
      {!data && !error && (
        <div className="mt-2" role="status" aria-busy="true" aria-label="Loading your checks">
          {[0, 1, 2, 3].map((i) => (
            <div key={i} className="flex min-h-14 items-center justify-between gap-4 border-b py-2">
              <div className="flex flex-col gap-1.5">
                <Skeleton className="h-4 w-40" />
                <Skeleton className="h-3.5 w-28 md:hidden" />
              </div>
              <Skeleton className="hidden h-4 w-36 sm:block" />
              <Skeleton className="h-5 w-8" />
            </div>
          ))}
        </div>
      )}
      {data && mine.length === 0 && !more && (
        <div className="py-16">
          <p className="text-lg font-medium">You haven't checked a store yet.</p>
          <p className="mt-1 text-muted-foreground">Paste your store's link and we'll show you what AI shoppers see.</p>
          <Button className="mt-6 h-11" onClick={() => go("/")}>
            Check my store
          </Button>
        </div>
      )}
      {mine.length > 0 && (
        <table className="w-full border-collapse text-left">
          <thead className="sr-only sm:not-sr-only">
            <tr className="border-b text-[13px] text-muted-foreground">
              <th className="py-3 pr-4 font-medium">Store</th>
              <th className="hidden py-3 pr-4 font-medium md:table-cell">Checked</th>
              <th className="hidden py-3 pr-4 font-medium sm:table-cell">Result</th>
              <th className="py-3 pr-4 text-right font-medium">Score</th>
              <th className="py-3">
                <span className="sr-only">Delete</span>
              </th>
            </tr>
          </thead>
          <tbody>
            {mine.map((r) => (
              <tr key={r.id} className="group border-b transition-colors hover:bg-panel">
                <td className="py-0 pr-4">
                  <a href={`#/run/${r.id}`} className="flex min-h-14 flex-col justify-center py-2 text-foreground no-underline">
                    <span className="font-medium [overflow-wrap:anywhere]">{name(r)}</span>
                    <span className="text-[13px] text-muted-foreground md:hidden">{checkedAt(r.started_at)}</span>
                  </a>
                </td>
                <td className="hidden pr-4 text-muted-foreground md:table-cell">{checkedAt(r.started_at)}</td>
                <td className="hidden pr-4 sm:table-cell">
                  <StatusLine level={running(r) ? "unknown" : level(r)} text={state(r)} className="text-sm font-normal" />
                </td>
                <td className="num pr-4 text-right text-lg">{r.score ?? "–"}</td>
                <td className="w-12 text-right">
                  <Button
                    variant="ghost"
                    size="icon"
                    className="size-11 text-muted-foreground"
                    aria-label={`Delete the check of ${name(r)} from ${checkedAt(r.started_at)}`}
                    disabled={running(r)}
                    onClick={() => setConfirm(r)}
                  >
                    <Trash2 aria-hidden />
                  </Button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {more && (
        <div className="mt-4">
          <Button variant="outline" className="h-11 border-line px-6" onClick={showMore} disabled={loadingMore}>
            {loadingMore ? "Loading…" : "Show more"}
          </Button>
        </div>
      )}
      {data && mine.length > 0 && health.data && (
        <p className="mt-4 text-sm text-muted-foreground">
          Checks are kept for {health.data.retention_days} days. Clearing your browser's cookies also removes them from this list.
        </p>
      )}

      <Dialog open={!!confirm} onOpenChange={(open) => !open && setConfirm(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle className="text-lg tracking-[-0.01em]">Delete this check?</DialogTitle>
            <DialogDescription>
              The results and screenshots for {confirm && name(confirm)} will be removed for good. This can't be undone.
            </DialogDescription>
          </DialogHeader>
          {deleteError && <p role="alert" className="text-sm text-bad">{deleteError}</p>}
          <DialogFooter>
            <Button variant="outline" className="h-10 border-line" onClick={() => setConfirm(null)}>
              Keep it
            </Button>
            <Button variant="destructive" className="h-10" onClick={remove} disabled={busy}>
              {busy ? "Deleting…" : "Delete"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
