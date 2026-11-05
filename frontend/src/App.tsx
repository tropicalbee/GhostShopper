import { Ghost, History, RotateCw } from "lucide-react";
import { lazy, Suspense } from "react";

import { Panel } from "@/components/bits";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { api, type Run } from "@/lib/api";
import { go, useFetch, useMediaQuery, useRoute } from "@/lib/hooks";
import { Compare } from "@/screens/Compare";
import { Home } from "@/screens/Home";
import { Live } from "@/screens/Live";
import { MyChecks } from "@/screens/MyChecks";
import { Results } from "@/screens/Results";

// AG Grid and the charts are most of the bundle; phones on the Simple view never load them.
const Advanced = lazy(() => import("@/screens/Advanced").then((m) => ({ default: m.Advanced })));

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
  const runs = useFetch(api.runs, [id, finished]);
  const wide = useMediaQuery("(min-width: 1024px)");

  if (run.error && !run.data) {
    if (run.status !== 404) return <Down retry={run.retry} />;
    return (
      <Panel className="mx-auto mt-10 max-w-md py-10 text-center">
        <p className="text-lg font-medium">We couldn't find that check.</p>
        <p className="mt-2 text-sm text-muted-foreground">It may have been deleted, or it was made in another browser.</p>
        <Button className="mt-6 h-11" onClick={() => go("/checks")}>
          See my checks
        </Button>
      </Panel>
    );
  }
  if (!run.data || !health.data) return <Skeleton className="mx-auto h-[28rem] max-w-2xl rounded-xl" />;
  if (isRunning(run.data)) return <Live run={run.data} />;
  if (advanced && wide)
    return (
      <Suspense fallback={<Skeleton className="h-[40rem] rounded-xl" />}>
        <Advanced run={run.data} runs={runs.data ?? []} health={health.data} />
      </Suspense>
    );
  return <Results run={run.data} health={health.data} runs={runs.data ?? []} wide={wide} />;
}

export default function App() {
  const route = useRoute();
  const health = useFetch(api.health, []);
  const runId = route[0] === "run" ? Number(route[1]) : 0;

  let screen;
  if (runId && route[2] === "compare") screen = <Compare runId={runId} />;
  else if (runId) screen = <RunScreen id={runId} advanced={route[2] === "advanced"} />;
  else if (route[0] === "checks") screen = <MyChecks />;
  else if (health.error) screen = <Down retry={health.retry} />;
  else if (health.data) screen = <Home />;
  else screen = <Skeleton className="mx-auto mt-24 h-72 max-w-xl rounded-xl" />;

  return (
    <div className="min-h-dvh">
      <header className="mx-auto flex max-w-7xl items-center justify-between px-4 py-4 sm:px-8">
        <button type="button" onClick={() => go("/")} className="flex min-h-11 items-center gap-2 font-semibold tracking-tight">
          <Ghost className="size-5" aria-hidden />
          GhostShopper
        </button>
        <nav className="flex items-center gap-1 text-sm">
          <Button variant="ghost" className="h-11" onClick={() => go("/checks")}>
            <History aria-hidden />
            My checks
          </Button>
        </nav>
      </header>
      <main className="mx-auto max-w-7xl px-4 pb-16 sm:px-8">{screen}</main>
    </div>
  );
}
