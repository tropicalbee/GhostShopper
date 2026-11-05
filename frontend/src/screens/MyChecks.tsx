import { ChevronRight, Plus, Trash2 } from "lucide-react";
import { useState } from "react";

import { hostOf, Panel } from "@/components/bits";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Skeleton } from "@/components/ui/skeleton";
import { api, type RunSummary } from "@/lib/api";
import { go, useFetch } from "@/lib/hooks";

const date = (iso: string) =>
  new Date(iso).toLocaleString(undefined, { day: "numeric", month: "short", hour: "numeric", minute: "2-digit" });

function name(r: RunSummary) {
  return r.live ? hostOf(r.store_url) : "Demo store (Fernhill Ceramics)";
}

export function MyChecks() {
  const { data, error, retry } = useFetch(api.runs, []);
  const health = useFetch(api.health, []);
  const [confirm, setConfirm] = useState<RunSummary | null>(null);
  const [busy, setBusy] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);

  const remove = async () => {
    if (!confirm) return;
    setBusy(true);
    setDeleteError(null);
    try {
      await api.deleteRun(confirm.id);
      setConfirm(null);
      retry();
    } catch (e) {
      setDeleteError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const mine = data?.filter((r) => r.mine) ?? [];
  return (
    <div className="mx-auto flex max-w-2xl flex-col gap-5">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight sm:text-3xl">My checks</h1>
          <p className="mt-1 text-sm text-muted-foreground">Saved in this browser only. Other people can't see them.</p>
        </div>
        <Button className="h-11" onClick={() => go("/")}>
          <Plus aria-hidden />
          New check
        </Button>
      </div>

      {error && <p role="alert" className="text-sm text-bad">{error}</p>}
      {!data && !error && <Skeleton className="h-48 rounded-xl" />}
      {data && mine.length === 0 && (
        <Panel className="py-10 text-center">
          <p className="text-lg font-medium">You haven't checked a store yet.</p>
          <Button className="mt-6 h-12" onClick={() => go("/")}>
            Check my store
          </Button>
        </Panel>
      )}
      {mine.length > 0 && (
        <ul className="divide-y rounded-xl border bg-card">
          {mine.map((r) => (
            <li key={r.id} className="flex items-center gap-2 pr-2">
              <button
                type="button"
                onClick={() => go(`/run/${r.id}`)}
                className="flex min-h-16 flex-1 items-center gap-4 rounded-l-xl px-4 py-3 text-left hover:bg-muted/50"
              >
                <span className="w-12 text-2xl font-semibold tabular-nums">{r.score ?? "–"}</span>
                <span className="min-w-0 flex-1">
                  <span className="block truncate font-medium">{name(r)}</span>
                  <span className="block text-sm text-muted-foreground">
                    {date(r.started_at)}
                    {r.status === "running" || r.status === "awaiting_human" ? " · Still checking" : ""}
                    {r.status === "error" ? " · Didn't finish" : ""}
                  </span>
                </span>
                <ChevronRight className="size-4 text-muted-foreground" aria-hidden />
              </button>
              <Button
                variant="ghost"
                size="icon-lg"
                className="size-11 text-muted-foreground"
                aria-label={`Delete the check of ${name(r)} from ${date(r.started_at)}`}
                disabled={r.status === "running" || r.status === "awaiting_human"}
                onClick={() => setConfirm(r)}
              >
                <Trash2 aria-hidden />
              </Button>
            </li>
          ))}
        </ul>
      )}
      {data && mine.length > 0 && health.data && (
        <p className="text-sm text-muted-foreground">
          Checks are kept for {health.data.retention_days} days. Clearing your browser's cookies also removes them from this list.
        </p>
      )}

      <Dialog open={!!confirm} onOpenChange={(open) => !open && setConfirm(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Delete this check?</DialogTitle>
            <DialogDescription>
              The results and screenshots for {confirm && name(confirm)} will be removed for good. This can't be undone.
            </DialogDescription>
          </DialogHeader>
          {deleteError && <p role="alert" className="text-sm text-bad">{deleteError}</p>}
          <DialogFooter>
            <Button variant="outline" className="h-11" onClick={() => setConfirm(null)}>
              Keep it
            </Button>
            <Button variant="destructive" className="h-11" onClick={remove} disabled={busy}>
              {busy ? "Deleting…" : "Delete"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
