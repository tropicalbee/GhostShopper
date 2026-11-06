import { History, Menu, Plus, SlidersHorizontal } from "lucide-react";
import { useMemo, useState, type ReactNode } from "react";

import { checkedAt, Logo, storeName } from "@/components/bits";
import { Skeleton } from "@/components/ui/skeleton";
import { Sheet, SheetContent, SheetDescription, SheetTitle, SheetTrigger } from "@/components/ui/sheet";
import type { Health, RunSummary } from "@/lib/api";
import { cn } from "@/lib/utils";

function Item({ href, on, icon, children, onNavigate }: { href: string; on: boolean; icon: ReactNode; children: ReactNode; onNavigate?: () => void }) {
  return (
    <a
      href={href}
      onClick={onNavigate}
      aria-current={on ? "page" : undefined}
      className={cn(
        "flex min-h-10 items-center gap-2.5 px-3 text-sm font-medium no-underline transition-colors [&_svg]:size-4 [&_svg]:shrink-0",
        on ? "bg-panel text-foreground" : "text-muted-foreground hover:bg-panel hover:text-foreground",
      )}
    >
      {icon}
      {children}
    </a>
  );
}

function Brand() {
  return (
    <a href="#/" className="flex h-14 shrink-0 items-center gap-3 border-b px-5 text-foreground no-underline">
      <Logo />
      <span className="text-[15px] font-semibold tracking-[-0.01em]">GhostShopper</span>
    </a>
  );
}

// The menu itself: the same on the desktop rail and in the phone drawer.
function NavBody({ route, runs, health, onNavigate }: { route: string[]; runs: RunSummary[] | null; health: Health | null; onNavigate?: () => void }) {
  const runId = route[0] === "run" ? Number(route[1]) : 0;
  const recent = useMemo(() => (runs ?? []).filter((r) => r.mine).slice(0, 6), [runs]);
  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <nav aria-label="Main" className="flex flex-col gap-0.5 p-3">
        <Item href="#/" on={route.length === 0} icon={<Plus />} onNavigate={onNavigate}>
          New check
        </Item>
        <Item href="#/checks" on={route[0] === "checks"} icon={<History />} onNavigate={onNavigate}>
          My checks
        </Item>
      </nav>
      <section aria-labelledby="recent-checks" className="min-h-0 flex-1 overflow-y-auto border-t px-3 py-4">
        <h2 id="recent-checks" className="px-3 text-[13px] font-medium text-muted-foreground">
          Recent checks
        </h2>
        {runs === null ? (
          <ul className="mt-2 flex flex-col gap-0.5" aria-busy="true" aria-label="Loading your recent checks">
            {[0, 1, 2].map((i) => (
              <li key={i} className="flex min-h-10 flex-col justify-center gap-1.5 px-3 py-1.5">
                <Skeleton className="h-3.5 w-28" />
                <Skeleton className="h-3 w-36" />
              </li>
            ))}
          </ul>
        ) : recent.length ? (
          <ul className="mt-2 flex flex-col gap-0.5">
            {recent.map((r) => (
              <li key={r.id}>
                <a
                  href={`#/run/${r.id}`}
                  onClick={onNavigate}
                  aria-current={r.id === runId ? "page" : undefined}
                  className={cn(
                    "flex min-h-10 items-center justify-between gap-3 px-3 text-sm no-underline transition-colors",
                    r.id === runId ? "bg-panel text-foreground" : "text-foreground/80 hover:bg-panel hover:text-foreground",
                  )}
                >
                  <span className="flex min-w-0 flex-col py-1.5">
                    <span className="truncate">{storeName({ live: !!r.live, store_url: r.store_url })}</span>
                    <span className="text-xs text-muted-foreground">
                      {r.status === "running" || r.status === "awaiting_human" ? `Check ${r.id}, running` : `Check ${r.id}, ${checkedAt(r.started_at)}`}
                    </span>
                  </span>
                  {r.score != null && <span className="num shrink-0 text-[13px] text-muted-foreground">{r.score}</span>}
                </a>
              </li>
            ))}
          </ul>
        ) : (
          <p className="mt-2 px-3 text-sm text-muted-foreground">Your checks will show up here.</p>
        )}
      </section>
      <div className="border-t p-3">
        {health?.demo_admin_open && (
          <Item href="/store/admin" on={false} icon={<SlidersHorizontal />}>
            Demo store settings
          </Item>
        )}
        <p className="px-3 pt-2 text-xs text-muted-foreground">PayPal sandbox only. We never pay on real stores.</p>
      </div>
    </div>
  );
}

export function Sidebar(props: { route: string[]; runs: RunSummary[] | null; health: Health | null }) {
  return (
    <aside className="sticky top-0 hidden h-dvh w-60 shrink-0 flex-col border-r bg-background lg:flex">
      <Brand />
      <NavBody {...props} />
    </aside>
  );
}

export function MobileBar(props: { route: string[]; runs: RunSummary[] | null; health: Health | null }) {
  const [open, setOpen] = useState(false);
  return (
    <header className="sticky top-0 z-40 flex h-14 items-center justify-between border-b bg-background pr-2 lg:hidden">
      <a href="#/" className="flex items-center gap-3 px-4 text-foreground no-underline">
        <Logo />
        <span className="text-[15px] font-semibold tracking-[-0.01em]">GhostShopper</span>
      </a>
      <Sheet open={open} onOpenChange={setOpen}>
        <SheetTrigger asChild>
          <button type="button" aria-label="Open the menu" className="grid size-11 place-items-center text-foreground">
            <Menu className="size-5" aria-hidden />
          </button>
        </SheetTrigger>
        <SheetContent side="left" className="w-72 gap-0 p-0">
          <SheetTitle className="sr-only">Menu</SheetTitle>
          <SheetDescription className="sr-only">Start a check or open one of your checks.</SheetDescription>
          <Brand />
          <NavBody {...props} onNavigate={() => setOpen(false)} />
        </SheetContent>
      </Sheet>
    </header>
  );
}
