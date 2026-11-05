import { CircleAlert, CircleCheck, Hand, Info, Loader2 } from "lucide-react";

import { ModeLabels, PathStrip, STAGES, storeName, Tag, type PathStage } from "@/components/bits";
import { api, type FeedLine, type Rubric, type Run } from "@/lib/api";
import { useFetch } from "@/lib/hooks";
import { cn } from "@/lib/utils";

const TONE = {
  good: { icon: CircleCheck, cls: "text-good", word: "Good" },
  bad: { icon: CircleAlert, cls: "text-bad", word: "Problem" },
  info: { icon: Info, cls: "text-muted-foreground", word: "Note" },
  neutral: { icon: null, cls: "", word: "" },
} as const;

function Line({ line }: { line: FeedLine }) {
  const tone = TONE[line.tone];
  const Icon = tone.icon;
  return (
    <li className="feed-in grid grid-cols-[2.5rem_1.5rem_minmax(0,1fr)] items-start border-b py-3 last:border-b-0">
      <span className="num pt-px text-[13px] text-muted-foreground">{line.step}</span>
      {Icon ? (
        <Icon className={cn("mt-0.5 size-[18px]", tone.cls)} aria-label={tone.word} />
      ) : (
        <span className="mt-2 ml-1.5 size-1.5 bg-line" aria-hidden />
      )}
      <span className={cn(line.tone === "neutral" && "text-muted-foreground", line.tone === "bad" && "text-bad")}>
        {line.text}
        {line.tone === "info" && <span className="text-muted-foreground"> (not your store's fault)</span>}
      </span>
    </li>
  );
}

// The path fills as checks come in: a stage is reached once any of its checks is logged, filled by the
// share of its checks that passed, and marked stuck when the store caused a failure there.
function livePath(run: Run, rubric: Rubric): PathStage[] {
  return STAGES.map(([key, name]) => {
    const r = rubric.stages.find((s) => s.key === key);
    const logged = run.checks.filter((c) => c.stage === key);
    const passed = logged.filter((c) => c.status === "pass").length;
    const stuck = logged.some((c) => c.status === "fail" && c.cause === "store");
    return { key, name, points: r?.points ?? 0, fill: r?.checks ? Math.min(1, passed / r.checks) : 0, state: stuck ? "stuck" : logged.length ? "reached" : "idle" } as PathStage;
  });
}

export function Live({ run }: { run: Run }) {
  const rubric = useFetch(api.rubric, []);
  return (
    <div className="max-w-3xl pt-10">
      <h1 className="flex items-center gap-3 border-b-[1.5px] border-rule pb-5 text-[1.875rem] leading-tight font-semibold tracking-[-0.03em]">
        <Loader2 className="size-6 shrink-0 animate-spin text-muted-foreground motion-reduce:animate-none" aria-hidden />
        <span className="min-w-0 [overflow-wrap:anywhere]">Checking {storeName(run)}…</span>
      </h1>
      <div className="mt-4 flex flex-wrap gap-2">
        <Tag>{run.live ? "Live store, checked up to the PayPal button" : "Demo store"}</Tag>
        <ModeLabels run={run} />
      </div>
      {rubric.data && (
        <div className="mt-8">
          <PathStrip stages={livePath(run, rubric.data)} detail={false} label="How far the shopper has got" />
        </div>
      )}

      {run.status === "awaiting_human" && run.awaiting && (
        <section className="mt-6 border border-warn/40 bg-panel p-5">
          <p className="flex items-center gap-2 font-medium">
            <Hand className="size-5 text-warn" aria-hidden />
            PayPal needs a person for a moment
          </p>
          <p className="mt-2 text-sm">{run.awaiting.reason}</p>
          <p className="mt-1 text-sm text-muted-foreground">{run.awaiting.instructions}</p>
        </section>
      )}

      <ol aria-live="polite" aria-label="What the shopper is doing" className="mt-6">
        {run.feed.map((line, i) => (
          <Line key={i} line={line} />
        ))}
        {!run.feed.length && <li className="py-3 text-muted-foreground">Opening your store…</li>}
      </ol>
      <p className="mt-6 border-t pt-4 text-sm text-muted-foreground">This usually takes under a minute. You can keep this page open.</p>
    </div>
  );
}
