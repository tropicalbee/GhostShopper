import { Check, ChevronDown, ExternalLink, HelpCircle, Minus, X } from "lucide-react";
import type { ReactNode } from "react";

import { Label, StatusLine } from "@/components/bits";
import type { PayPalItem, PayPalReadiness as Readiness, Run } from "@/lib/api";
import { cn } from "@/lib/utils";

const STATUS: Record<PayPalItem["status"], { word: string; tone: string; icon: ReactNode }> = {
  detected: { word: "Found", tone: "text-good", icon: <Check className="size-4" aria-hidden /> },
  partial: { word: "Partly", tone: "text-warn", icon: <Minus className="size-4" aria-hidden /> },
  not_confirmed: { word: "Not confirmed", tone: "text-warn", icon: <HelpCircle className="size-4" aria-hidden /> },
  missing: { word: "Missing", tone: "text-bad", icon: <X className="size-4" aria-hidden /> },
};

const VERDICT = {
  good: "PayPal is set up well for AI shoppers",
  warn: "PayPal works, but AI shoppers could have an easier time",
  bad: "PayPal is hard for AI shoppers to use here",
} as const;

// Each segment is as wide as the points it is worth, like the shopper's path: filled for points earned.
function Meter({ items }: { items: PayPalItem[] }) {
  return (
    <div className="flex h-3 gap-px" role="img" aria-label="Points earned for each PayPal signal">
      {items.map((i) => (
        <div key={i.key} className="relative border" style={{ flexGrow: i.max, flexBasis: 0 }} title={`${i.label}: ${i.points} of ${i.max}`}>
          <div className="absolute inset-y-0 left-0 bg-earned" style={{ width: `${(i.points / i.max) * 100}%` }} />
        </div>
      ))}
    </div>
  );
}

function Row({ item }: { item: PayPalItem }) {
  const s = STATUS[item.status];
  return (
    <li className="border-b last:border-b-0">
      <details className="group">
        <summary className="flex min-h-11 cursor-pointer list-none items-center gap-3 py-2 [&::-webkit-details-marker]:hidden" title={item.note}>
          <span className={cn("flex w-32 shrink-0 items-center gap-1.5 text-[13px] font-medium sm:w-36", s.tone)}>
            {s.icon}
            {s.word}
          </span>
          <span className="min-w-0 flex-1 truncate">{item.label}</span>
          <span className="num shrink-0 text-[13px] text-muted-foreground">
            {item.points}/{item.max}
          </span>
          <ChevronDown className="size-4 shrink-0 text-muted-foreground transition-transform group-open:rotate-180" aria-hidden />
        </summary>
        <div className="pb-3 text-sm text-muted-foreground sm:pl-[9.5rem]">
          <p>{item.note}</p>
          {item.evidence.length > 0 && (
            <ul className="mt-1.5 space-y-0.5">
              {item.evidence.map((e) => (
                <li key={e} className="num break-all text-[12px] text-foreground/80">
                  {e}
                </li>
              ))}
            </ul>
          )}
        </div>
      </details>
    </li>
  );
}

function Body({ r }: { r: Readiness }) {
  const steps = r.steps_to_paypal;
  const facts: string[] = [];
  if (r.sdk) facts.push(`SDK ${r.sdk.version}${r.sdk.mock ? " (practice run)" : ""}`);
  if (steps != null) facts.push(steps === 0 ? "PayPal on the product page" : `${steps} ${steps === 1 ? "page" : "pages"} to PayPal`);
  facts.push(`${r.pages_scanned.length} ${r.pages_scanned.length === 1 ? "page" : "pages"} checked`);
  return (
    <>
      <div className="mt-4 grid items-end gap-x-8 gap-y-3 sm:grid-cols-[auto_minmax(0,1fr)]">
        <p className="num text-[3.5rem] leading-none font-medium tracking-tight">
          {r.score}
          <span className="text-xl text-muted-foreground"> / 100</span>
        </p>
        <div>
          <StatusLine level={r.status} text={r.paypal_found ? VERDICT[r.status] : "No PayPal found on this store"} />
          <p className="mt-1 text-[13px] text-muted-foreground">{facts.join(" · ")}</p>
        </div>
      </div>
      <div className="mt-5">
        <Meter items={r.checklist} />
      </div>
      <ul className="mt-4 border-t">
        {r.checklist.map((i) => (
          <Row key={i.key} item={i} />
        ))}
      </ul>
      {r.recommendations.length > 0 && (
        <div className="mt-6">
          <h3 className="text-[15px] font-semibold tracking-[-0.01em]">What to change</h3>
          <ol className="mt-2 border-t">
            {r.recommendations.map((rec) => (
              <li key={rec.key} className="grid grid-cols-[minmax(0,1fr)_auto] gap-x-4 border-b py-3.5">
                <div>
                  <p className="font-medium">{rec.title}</p>
                  <p className="mt-0.5 text-sm text-muted-foreground">{rec.why}</p>
                  <a
                    href={rec.docs_url}
                    target="_blank"
                    rel="noreferrer"
                    className="mt-1.5 inline-flex min-h-11 items-center gap-1.5 text-sm font-medium underline decoration-line underline-offset-4 hover:decoration-foreground sm:min-h-0"
                  >
                    PayPal docs
                    <ExternalLink className="size-3.5" aria-hidden />
                  </a>
                </div>
                {rec.key !== "add_paypal" && <span className="num h-fit border px-2 py-0.5 text-xs text-muted-foreground">+{rec.points}</span>}
              </li>
            ))}
          </ol>
        </div>
      )}
    </>
  );
}

// run.paypal_readiness is null for checks made before this panel existed, and while a check is still running.
export function PayPalReadiness({ run, className }: { run: Run; className?: string }) {
  const r = run.paypal_readiness;
  const running = run.status === "running" || run.status === "awaiting_human";
  return (
    <section className={cn("border bg-card p-6", className)} aria-labelledby="pp-ready">
      <Label className="text-[15px]" aside={r ? "Read from the pages the shopper visited" : undefined}>
        <span id="pp-ready">PayPal readiness</span>
      </Label>
      {r ? (
        <Body r={r} />
      ) : (
        <p className="mt-3 text-muted-foreground">
          {running
            ? "We are looking at the PayPal setup as the shopper moves through the store."
            : "This check has no PayPal readiness. It was made before this panel existed, or the shopper never reached a page to read. Check the store again to see it."}
        </p>
      )}
    </section>
  );
}
