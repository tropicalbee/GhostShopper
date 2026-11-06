import { CircleCheck, TriangleAlert } from "lucide-react";

import { checkedAt, Label, PathSkeleton, ScoreFigure, ShopperPath, StatusLine, storeName } from "@/components/bits";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { api, type Run } from "@/lib/api";
import { go, useCountUp, useFetch } from "@/lib/hooks";
import { cn } from "@/lib/utils";

function Side({ title, run, score, muted }: { title: string; run: Run | null; score: number; muted?: boolean }) {
  return (
    <section className={cn("min-w-0 p-6", muted ? "bg-panel" : "bg-card")}>
      <Label aside={run ? `Check ${run.id}, ${checkedAt(run.started_at)}` : undefined}>{title}</Label>
      <ScoreFigure score={score} className={cn("mt-5 text-[4.5rem] sm:text-[5.5rem]", muted && "text-foreground/70")} />
      {run?.scorecard ? (
        <>
          <StatusLine level={run.scorecard.simple.status} text={run.scorecard.simple.status_text} className="mt-4" />
          <div className="mt-6">
            <ShopperPath card={run.scorecard} compact />
          </div>
        </>
      ) : (
        !run && (
          <div aria-hidden>
            <Skeleton className="mt-4 h-5 w-48 max-w-full" />
            <div className="mt-6">
              <PathSkeleton compact />
            </div>
          </div>
        )
      )}
    </section>
  );
}

// The shape of the page while the comparison loads: heading rule, two score panels, two lists.
function CompareSkeleton() {
  return (
    <div role="status" aria-busy="true" aria-label="Loading the comparison">
      <div className="border-b-[1.5px] border-rule pt-8 pb-5">
        <Skeleton className="h-4 w-44" />
        <Skeleton className="mt-3 h-8 w-80 max-w-full" />
      </div>
      <div className="mt-6 grid border md:grid-cols-[minmax(0,1fr)_9rem_minmax(0,1fr)]">
        {[0, 1, 2].map((i) =>
          i === 1 ? (
            <div key={i} className="grid place-items-center border-y px-6 py-4 md:border-x md:border-y-0">
              <Skeleton className="h-8 w-14" />
            </div>
          ) : (
            <div key={i} className={cn("p-6", i === 0 && "bg-panel")}>
              <Skeleton className="h-4 w-24" />
              <Skeleton className="mt-5 h-20 w-40" />
              <Skeleton className="mt-4 h-5 w-48 max-w-full" />
              <div className="mt-6">
                <PathSkeleton compact />
              </div>
            </div>
          ),
        )}
      </div>
      <div className="mt-10 grid gap-10 md:grid-cols-2">
        {[0, 1].map((i) => (
          <div key={i}>
            <Skeleton className="h-6 w-32" />
            <div className="mt-3 border-t-[1.5px] border-rule">
              {[0, 1, 2].map((j) => (
                <div key={j} className="border-b py-3.5">
                  <Skeleton className="h-4 w-4/5" />
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

// This check against the previous check of the same store from this browser.
export function Compare({ runId }: { runId: number }) {
  const { data, error } = useFetch(() => api.compareFor(runId), [runId]);
  const after = useCountUp(data?.after.score ?? 0, data?.before.score ?? 0, 1600);
  // Compare items carry technical titles; the plain words come from the runs' scorecards.
  const beforeRun = useFetch(() => (data ? api.run(data.before.run_id) : Promise.resolve(null)), [data?.before.run_id]);
  const afterRun = useFetch(() => (data ? api.run(data.after.run_id) : Promise.resolve(null)), [data?.after.run_id]);
  const plain = (run: Run | null, check: string) => run?.scorecard?.fixes.find((f) => f.check === check)?.plain;
  const plainHow = (check: string) => plain(afterRun.data, check)?.how;
  const plainTitle = (f: { check: string; title: string }) =>
    plain(afterRun.data, f.check)?.title ?? plain(beforeRun.data, f.check)?.title ?? f.title;

  if (error) {
    return (
      <div className="max-w-xl pt-16">
        <p className="text-lg font-medium">{error}</p>
        <Button className="mt-6 h-11" onClick={() => go(`/run/${runId}`)}>
          Back to the results
        </Button>
      </div>
    );
  }
  if (!data) return <CompareSkeleton />;

  const delta = data.score_change;
  const stillToFix = [...data.remaining, ...data.new_failures];
  // Titles come from the two runs; until both have answered, show bars instead of the technical wording.
  const ready = (!!beforeRun.data || !!beforeRun.error) && (!!afterRun.data || !!afterRun.error);
  const title = (f: { check: string; title: string }) => (ready ? plainTitle(f) : <Skeleton className="my-1 h-4 w-3/4" />);
  const name = afterRun.data ? storeName(afterRun.data) : "";
  return (
    <div>
      <header className="pt-8">
        <p className="flex gap-2 text-[13px] text-muted-foreground">
          <a href={`#/run/${runId}`} className="text-muted-foreground no-underline hover:text-foreground">
            Check {runId}
          </a>
          <span aria-hidden>/</span>
          <span className="text-foreground">Before and after</span>
        </p>
        <div className="flex flex-col gap-2 border-b-[1.5px] border-rule pt-2 pb-5 sm:flex-row sm:items-end sm:justify-between">
          <h1 className="text-[1.875rem] leading-tight font-semibold tracking-[-0.03em]">Before and after your fixes</h1>
          {name && <p className="text-muted-foreground">{name}</p>}
        </div>
      </header>

      <div className="mt-6 grid border md:grid-cols-[minmax(0,1fr)_9rem_minmax(0,1fr)]">
        <Side title="Before" run={beforeRun.data} score={data.before.score} muted />
        <div className="flex flex-row items-center justify-center gap-2 border-y px-6 py-4 md:flex-col md:border-x md:border-y-0">
          <span className={cn("num text-3xl", delta > 0 ? "text-good" : delta < 0 ? "text-bad" : "text-muted-foreground")}>
            {delta > 0 ? "+" : delta < 0 ? "−" : ""}
            {Math.abs(delta)}
          </span>
          <span className="text-[13px] text-muted-foreground">points</span>
        </div>
        <Side title="After" run={afterRun.data} score={after} />
      </div>

      {data.after.outcome === "purchased" && data.after.order_id && (
        <p className="mt-4 flex items-center gap-2 border px-4 py-3">
          <CircleCheck className="size-4 text-good" aria-hidden />
          The AI shopper bought the product and the PayPal payment went through.
        </p>
      )}

      <div className="mt-10 grid gap-10 md:grid-cols-2">
        <section>
          <h2 className="flex items-baseline justify-between border-b-[1.5px] border-rule pb-3 text-lg font-semibold tracking-[-0.01em]">
            Fixed <span className="num text-sm font-normal text-muted-foreground">{data.fixed.length}</span>
          </h2>
          <ul>
            {data.fixed.map((f) => (
              <li key={f.check} className="flex items-start gap-2.5 border-b py-3">
                <CircleCheck className="mt-0.5 size-4 shrink-0 text-good" aria-label="Fixed" />
                <span className="min-w-0 flex-1 text-muted-foreground line-through decoration-line">{title(f)}</span>
              </li>
            ))}
            {!data.fixed.length && <li className="py-3 text-muted-foreground">Nothing fixed yet.</li>}
          </ul>
        </section>
        <section>
          <h2 className="flex items-baseline justify-between border-b-[1.5px] border-rule pb-3 text-lg font-semibold tracking-[-0.01em]">
            Still to fix <span className="num text-sm font-normal text-muted-foreground">{stillToFix.length}</span>
          </h2>
          <ul>
            {stillToFix.map((f) => (
              <li key={f.check} className="border-b py-3">
                <div className="font-medium">{title(f)}</div>
                {plainHow(f.check) && <p className="mt-0.5 text-sm text-muted-foreground">{plainHow(f.check)}</p>}
              </li>
            ))}
            {!stillToFix.length && <li className="py-3 text-muted-foreground">Nothing left to fix.</li>}
          </ul>
        </section>
      </div>

      {data.warnings.map((w) => (
        <p key={w} className="mt-4 flex items-start gap-2 text-sm text-muted-foreground">
          <TriangleAlert className="mt-0.5 size-4 shrink-0" aria-hidden />
          {w}
        </p>
      ))}

      <Button variant="outline" className="mt-10 h-10 border-line" onClick={() => go(`/run/${data.after.run_id}`)}>
        See the latest results
      </Button>
    </div>
  );
}
