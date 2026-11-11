import { RotateCw } from "lucide-react";
import { lazy, Suspense } from "react";

import { Panel, RunSkeleton } from "@/components/bits";
import { AppBar } from "@/components/AppBar";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { api, RECENT_RUNS, type Run, type RunSummary } from "@/lib/api";
import { go, hashQuery, useFetch, useMediaQuery, useRoute } from "@/lib/hooks";
import { REPO_URL } from "@/lib/utils";
import { Compare } from "@/screens/Compare";
import { Landing } from "@/screens/Landing";
import { Live } from "@/screens/Live";
import { MyChecks } from "@/screens/MyChecks";
import { NewCheck } from "@/screens/NewCheck";
import { Results } from "@/screens/Results";

// AG Grid and the charts are most of the bundle; phones on the Simple view never load them.
const Advanced = lazy(() => import("@/screens/Advanced").then((m) => ({ default: m.Advanced })));

const Ledger = lazy(() => import("@/screens/Ledger").then((m) => ({ default: m.Ledger })));

const NO_RUNS: RunSummary[] = []; // a stable empty list, so Results' memo is not defeated while the list loads
const isRunning = (r: Run) => r.status === "running" || r.status === "awaiting_human";

function Down({ retry }: { retry: () => void }) {
  return (
    <Panel className="mx-auto mt-16 max-w-md py-10 text-center">
      <p className="text-lg font-medium">GhostShopper isn't responding</p>
      <p className="mt-2 text-sm text-muted-foreground">Check your internet connection, then try again.</p>
      <Button className="mt-6 h-11" onClick={retry}>
        <RotateCw aria-hidden />
        Retry
      </Button>
    </Panel>
  );
}

function RunScreen({ id, advanced }: { id: number; advanced: boolean }) {
  const health = useFetch(api.health, []);
  const run = useFetch(() => api.run(id), [id], 1000, isRunning);
  const finished = run.data && !isRunning(run.data);
  const runs = useFetch(() => api.runs({ limit: RECENT_RUNS }), [id, finished]);
  const wide = useMediaQuery("(min-width: 768px)"); // the Advanced view, from tablet width up

  if (run.error && !run.data) {
    if (run.status !== 404) return <Down retry={run.retry} />;
    return (
      <Panel className="mx-auto mt-16 max-w-md py-10 text-center">
        <p className="text-lg font-medium">We couldn't find that check.</p>
        <p className="mt-2 text-sm text-muted-foreground">It may have been deleted, or it was made in another browser.</p>
        <Button className="mt-6 h-11" onClick={() => go("/checks")}>
          See my checks
        </Button>
      </Panel>
    );
  }
  if (!run.data || !health.data) return <RunSkeleton />;
  if (isRunning(run.data)) return <Live run={run.data} />;
  if (advanced && wide)
    return (
      <Suspense fallback={<RunSkeleton />}>
        <Advanced run={run.data} runs={runs.data} health={health.data} />
      </Suspense>
    );
  return <Results run={run.data} health={health.data} runs={runs.data ?? NO_RUNS} wide={wide} />;
}

export default function App() {
  const route = useRoute();
  const health = useFetch(api.health, []);
  const runId = route[0] === "run" ? Number(route[1]) : 0;
  // Refetched on every route change, and every 2 s while one of your checks runs, so the menu stays current.
  const runs = useFetch(() => api.runs({ limit: RECENT_RUNS }), [route.join("/")], 2000, (rs) =>
    rs.some((r) => r.mine && (r.status === "running" || r.status === "awaiting_human")),
  );

  if (route.length === 0) return <Landing />;

  let screen;
  if (runId && route[2] === "compare") screen = <Compare runId={runId} />;
  else if (runId) screen = <RunScreen id={runId} advanced={route[2] === "advanced"} />;
  else if (route[0] === "checks") screen = <MyChecks />;
  else if (route[0] === "ledger")
    screen = (
      <Suspense fallback={<Skeleton className="mt-24 h-72 max-w-xl" />}>
        <Ledger />
      </Suspense>
    );
  else if (health.error) screen = <Down retry={health.retry} />;
  else {
    const yours = hashQuery().get("store") === "yours";
    screen = <NewCheck key={String(yours)} yours={yours} />;
  }

  // The most recent check, for the Advanced tab when no check is open.
  const advancedId = runId || (runs.data?.[0]?.id ?? null);
  return (
    <div className="flex min-h-dvh flex-col">
      <AppBar route={route} health={health.data} advancedId={advancedId} />
      <main className="mx-auto w-[min(1200px,100%-32px)] flex-1 pt-[30px] pb-20 sm:w-[min(1200px,100%-56px)]">{screen}</main>
      <footer className="border-t">
        <div className="mx-auto flex w-[min(1200px,100%-32px)] flex-wrap justify-between gap-x-6 gap-y-2 py-5 text-[13px] text-muted-foreground sm:w-[min(1200px,100%-56px)]">
          <p>Scores come from checks on what the browser saw, never from the AI.</p>
          <a href={REPO_URL} target="_blank" rel="noreferrer" className="text-muted-foreground no-underline transition-colors hover:text-foreground">
            Source on GitHub
          </a>
        </div>
      </footer>
    </div>
  );
}
