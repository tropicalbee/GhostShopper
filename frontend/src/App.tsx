import { RotateCw } from "lucide-react";
import { lazy, Suspense } from "react";

import { Panel, RunSkeleton } from "@/components/bits";
import { MobileBar, Sidebar } from "@/components/Nav";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { api, RECENT_RUNS, type Run, type RunSummary } from "@/lib/api";
import { go, useFetch, useMediaQuery, useRoute } from "@/lib/hooks";
import { Compare } from "@/screens/Compare";
import { Home } from "@/screens/Home";
import { Live } from "@/screens/Live";
import { MyChecks } from "@/screens/MyChecks";
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
  else if (health.data) screen = <Home />;
  else screen = <Skeleton className="mt-24 h-72 max-w-xl" />;

  // null while the list loads, so the menu shows a skeleton; a failed load shows the empty note instead.
  const nav = { route, runs: runs.data ?? (runs.error ? [] : null), health: health.data };
  return (
    <div className="flex min-h-dvh">
      <Sidebar {...nav} />
      <div className="flex min-w-0 flex-1 flex-col">
        <MobileBar {...nav} />
        <main className="mx-auto w-full max-w-[76rem] flex-1 px-4 pb-20 sm:px-8 lg:px-10">{screen}</main>
        <footer className="border-t">
          <p className="mx-auto max-w-[76rem] px-4 py-5 text-[13px] text-muted-foreground sm:px-8 lg:px-10">
            Scores come from checks on what the browser saw, never from the AI.
          </p>
        </footer>
      </div>
    </div>
  );
}
