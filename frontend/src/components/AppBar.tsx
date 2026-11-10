import { History, Landmark, Menu, Plus, SlidersHorizontal } from "lucide-react";
import { useState, type ReactNode } from "react";

import { Logo } from "@/components/bits";
import { Button } from "@/components/ui/button";
import { Sheet, SheetContent, SheetDescription, SheetTitle, SheetTrigger } from "@/components/ui/sheet";
import type { Health } from "@/lib/api";
import { cn } from "@/lib/utils";

type Tab = { key: string; href: string; icon: ReactNode; label: string; on: boolean };

function tabsFor(route: string[], advancedId: number | null): Tab[] {
  return [
    { key: "new", href: "#/new", icon: <Plus />, label: "New check", on: route[0] === "new" },
    { key: "checks", href: "#/checks", icon: <History />, label: "My checks", on: route[0] === "checks" || (route[0] === "run" && route[2] !== "advanced") },
    { key: "ledger", href: "#/ledger", icon: <Landmark />, label: "Sales ledger", on: route[0] === "ledger" },
    {
      key: "advanced",
      href: advancedId ? `#/run/${advancedId}/advanced` : "#/checks",
      icon: <SlidersHorizontal />,
      label: "Advanced",
      on: route[0] === "run" && route[2] === "advanced",
    },
  ];
}

export function PracticeChip({ health }: { health: Health | null }) {
  if (health?.paypal_mode !== "mock") return null;
  return (
    <span className="inline-flex items-center gap-1.5 rounded-full border border-[#262626] bg-[#141414] px-2.5 py-0.5 text-xs font-medium whitespace-nowrap text-muted-foreground">
      <span className="size-1.5 rounded-full bg-current" aria-hidden />
      Practice mode
    </span>
  );
}

function BrandLink() {
  return (
    <a href="#/" className="flex items-center gap-2.5 text-[15px] font-semibold tracking-[-0.03em] text-foreground no-underline">
      <Logo className="size-5" />
      GhostShopper
    </a>
  );
}

// The bar every app page shares: logo, the four tabs, the Practice mode chip, and on phones a menu sheet.
export function AppBar({ route, health, advancedId }: { route: string[]; health: Health | null; advancedId: number | null }) {
  const [open, setOpen] = useState(false);
  const tabs = tabsFor(route, advancedId);
  return (
    <header className="sticky top-0 z-30 border-b bg-black/95">
      <div className="mx-auto flex h-[60px] max-w-[1264px] items-center justify-between px-4 sm:px-7">
        <div className="flex items-center">
          <BrandLink />
          <nav aria-label="Main" className="ml-7 hidden gap-1 md:flex">
            {tabs.map((t) => (
              <a
                key={t.key}
                href={t.href}
                aria-current={t.on ? "page" : undefined}
                className={cn(
                  "flex items-center gap-[7px] rounded-lg px-[11px] py-[7px] text-[13.5px] no-underline transition-colors [&_svg]:size-[15px]",
                  t.on ? "bg-[#141414] text-foreground shadow-[inset_0_0_0_1px_#262626]" : "text-faint hover:bg-[#0f0f0f] hover:text-foreground",
                )}
              >
                {t.icon}
                {t.label}
              </a>
            ))}
          </nav>
        </div>
        <div className="flex items-center gap-2">
          <span className="hidden sm:inline-flex">
            <PracticeChip health={health} />
          </span>
          <Sheet open={open} onOpenChange={setOpen}>
            <SheetTrigger asChild>
              <Button variant="outline" size="icon" aria-label="Open the menu" className="size-11 bg-card md:hidden">
                <Menu aria-hidden />
              </Button>
            </SheetTrigger>
            <SheetContent side="left" className="w-72 gap-0 p-0">
              <SheetTitle className="sr-only">Menu</SheetTitle>
              <SheetDescription className="sr-only">Start a check or open your checks.</SheetDescription>
              <div className="flex h-[60px] items-center border-b px-5">
                <BrandLink />
              </div>
              <nav aria-label="Menu" className="flex flex-col gap-0.5 p-3">
                {tabs.map((t) => (
                  <a
                    key={t.key}
                    href={t.href}
                    onClick={() => setOpen(false)}
                    aria-current={t.on ? "page" : undefined}
                    className={cn(
                      "flex min-h-11 items-center gap-2.5 rounded-lg px-3 text-sm font-medium no-underline [&_svg]:size-4",
                      t.on ? "bg-[#141414] text-foreground" : "text-muted-foreground hover:text-foreground",
                    )}
                  >
                    {t.icon}
                    {t.label}
                  </a>
                ))}
              </nav>
              <div className="px-5 pt-2">
                <PracticeChip health={health} />
              </div>
              <p className="px-5 pt-4 text-xs text-muted-foreground">PayPal sandbox only. We never pay on real stores.</p>
            </SheetContent>
          </Sheet>
        </div>
      </div>
    </header>
  );
}
