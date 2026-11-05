import { ArrowRight, CircleCheck, CircleDashed, CreditCard, TriangleAlert } from "lucide-react";

import { Label, Panel, ScoreGauge } from "@/components/bits";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { api } from "@/lib/api";
import { go, useCountUp, useFetch } from "@/lib/hooks";

// This check against the previous check of the same store from this browser.
export function Compare({ runId }: { runId: number }) {
  const { data, error } = useFetch(() => api.compareFor(runId), [runId]);
  const after = useCountUp(data?.after.score ?? 0, data?.before.score ?? 0, 1600);
  // Compare items carry technical titles; the plain words come from the runs' scorecards.
  const beforeRun = useFetch(() => (data ? api.run(data.before.run_id) : Promise.resolve(null)), [data?.before.run_id]);
  const afterRun = useFetch(() => (data ? api.run(data.after.run_id) : Promise.resolve(null)), [data?.after.run_id]);
  const plain = (run: typeof afterRun.data, check: string) => run?.scorecard?.fixes.find((f) => f.check === check)?.plain;
  const plainHow = (check: string) => plain(afterRun.data, check)?.how;
  const plainTitle = (f: { check: string; title: string }) =>
    plain(afterRun.data, f.check)?.title ?? plain(beforeRun.data, f.check)?.title ?? f.title;

  if (error) {
    return (
      <Panel className="mx-auto max-w-xl py-10 text-center">
        <p className="text-lg font-medium">{error}</p>
        <Button className="mt-6 h-12" onClick={() => go(`/run/${runId}`)}>
          Back to the results
        </Button>
      </Panel>
    );
  }
  if (!data) return <Skeleton className="mx-auto h-96 max-w-3xl rounded-xl" />;

  const delta = data.score_change;
  const stillToFix = [...data.remaining, ...data.new_failures];
  return (
    <div className="mx-auto flex max-w-3xl flex-col gap-5">
      <h1 className="text-2xl font-semibold tracking-tight sm:text-3xl">Before and after your fixes</h1>

      <Panel className="grid items-end gap-6 py-8 sm:grid-cols-[1fr_auto_1fr]">
        <div className="text-center opacity-60">
          <p className="mb-2 text-sm font-medium text-muted-foreground uppercase">Before</p>
          <ScoreGauge score={data.before.score} size={200} />
        </div>
        <div className="flex flex-col items-center gap-1 pb-6">
          <ArrowRight className="hidden size-6 text-muted-foreground sm:block" aria-hidden />
          <span className={delta >= 0 ? "text-2xl font-semibold text-good" : "text-2xl font-semibold text-bad"}>
            {delta >= 0 ? "+" : ""}
            {delta}
          </span>
          <span className="text-xs text-muted-foreground">points</span>
        </div>
        <div className="text-center">
          <p className="mb-2 text-sm font-medium uppercase">After</p>
          <ScoreGauge score={after} size={200} />
        </div>
      </Panel>

      {data.after.outcome === "purchased" && data.after.order_id && (
        <p className="flex items-center gap-2 rounded-lg border bg-card p-4">
          <CreditCard className="size-5 text-good" aria-hidden />
          The AI shopper bought the product and the PayPal payment went through.
        </p>
      )}

      <div className="grid gap-5 sm:grid-cols-2">
        <Panel>
          <Label icon={CircleCheck}>Fixed ({data.fixed.length})</Label>
          <ul className="mt-3 flex flex-col gap-2">
            {data.fixed.map((f) => (
              <li key={f.check} className="flex items-start gap-2">
                <CircleCheck className="mt-0.5 size-4 shrink-0 text-good" aria-label="Fixed" />
                <span className="text-muted-foreground line-through decoration-muted-foreground/50">{plainTitle(f)}</span>
              </li>
            ))}
            {!data.fixed.length && <li className="text-muted-foreground">Nothing fixed yet.</li>}
          </ul>
        </Panel>
        <Panel>
          <Label icon={CircleDashed}>Still to fix ({stillToFix.length})</Label>
          <ul className="mt-3 flex flex-col gap-3">
            {stillToFix.map((f) => (
              <li key={f.check}>
                <p className="font-medium">{plainTitle(f)}</p>
                {plainHow(f.check) && <p className="text-sm text-muted-foreground">{plainHow(f.check)}</p>}
              </li>
            ))}
            {!stillToFix.length && <li className="text-muted-foreground">Nothing left. Well done.</li>}
          </ul>
        </Panel>
      </div>

      {data.warnings.map((w) => (
        <p key={w} className="flex items-start gap-2 text-sm text-muted-foreground">
          <TriangleAlert className="mt-0.5 size-4 shrink-0" aria-hidden />
          {w}
        </p>
      ))}

      <Button variant="outline" className="h-12 self-start" onClick={() => go(`/run/${data.after.run_id}`)}>
        See the latest results
      </Button>
    </div>
  );
}
