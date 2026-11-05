import { CircleAlert, CircleCheck, Hand, Info, Loader2 } from "lucide-react";

import { hostOf, ModeLabels, Panel } from "@/components/bits";
import type { FeedLine, Run } from "@/lib/api";
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
    <li className="feed-in flex items-start gap-3 py-2.5">
      {Icon ? (
        <Icon className={cn("mt-0.5 size-5 shrink-0", tone.cls)} aria-label={tone.word} />
      ) : (
        <span className="mt-2 size-1.5 shrink-0 translate-x-[7px] rounded-full bg-muted-foreground/50" aria-hidden />
      )}
      <span className={cn("text-base", line.tone === "neutral" && "text-muted-foreground")}>
        {line.text}
        {line.tone === "info" && <span className="text-muted-foreground"> (not your store's fault)</span>}
      </span>
    </li>
  );
}

export function Live({ run }: { run: Run }) {
  return (
    <div className="mx-auto max-w-xl pt-6 sm:pt-16">
      <h1 className="flex items-center gap-3 text-2xl font-semibold tracking-tight sm:text-3xl">
        <Loader2 className="size-6 animate-spin text-muted-foreground motion-reduce:animate-none" aria-hidden />
        Checking your store…
      </h1>
      <p className="mt-2 text-muted-foreground">{run.live ? hostOf(run.store_url) : "Demo store (Fernhill Ceramics)"}</p>
      <div className="mt-4">
        <ModeLabels run={run} />
      </div>

      {run.status === "awaiting_human" && run.awaiting && (
        <Panel className="mt-6 border-warn bg-warn/10">
          <p className="flex items-center gap-2 font-medium">
            <Hand className="size-5" aria-hidden />
            PayPal needs a person for a moment
          </p>
          <p className="mt-2 text-sm">{run.awaiting.reason}</p>
          <p className="mt-1 text-sm text-muted-foreground">{run.awaiting.instructions}</p>
        </Panel>
      )}

      <Panel className="mt-6">
        <ol aria-live="polite" className="divide-y">
          {run.feed.map((line, i) => (
            <Line key={i} line={line} />
          ))}
          {!run.feed.length && <li className="py-2.5 text-muted-foreground">Opening your store…</li>}
        </ol>
      </Panel>
      <p className="mt-4 text-sm text-muted-foreground">This usually takes under a minute. You can keep this page open.</p>
    </div>
  );
}
