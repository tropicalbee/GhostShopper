import { ArrowRight, ShieldCheck } from "lucide-react";
import { useState, type FormEvent } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { startCheck } from "@/lib/api";
import { go } from "@/lib/hooks";


// What the shopper looks for, in the order it shops.
const CHECKS = [
  ["Can it find your product?", "From your home page, by its name."],
  ["Can it read the price and stock?", "As text, with the currency."],
  ["Can it tell which button buys?", "One clear Buy now or Add to cart."],
  ["Can it reach your PayPal button?", "Without extra forms on the way."],
];

export function Home() {
  const [url, setUrl] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [budget, setBudget] = useState("");
  const [budgetError, setBudgetError] = useState<string | null>(null);

  const start = async (storeUrl: string | null) => {
    const limit = budget.trim().replace(/^\$/, "");
    if (!storeUrl && limit && !(/^\d{1,5}(\.\d{1,2})?$/.test(limit) && Number(limit) > 0)) {
      setBudgetError("Type an amount in dollars above 0, like 30 or 24.50, or leave it empty.");
      return;
    }
    setBudgetError(null);
    setBusy(true);
    setError(null);
    try {
      const { run_id } = await startCheck(storeUrl, storeUrl ? null : limit);
      go(`/run/${run_id}`);
    } catch (e) {
      setError((e as Error).message);
      setBusy(false);
    }
  };

  const submit = (e: FormEvent) => {
    e.preventDefault();
    const value = url.trim();
    if (!value) {
      setError("Type your store's web address first, for example myshop.com");
      return;
    }
    start(/^https?:\/\//i.test(value) ? value : `https://${value}`);
  };

  return (
    <div className="pt-12 sm:pt-20">
      <div className="max-w-2xl">
        <h1 className="text-[2.25rem] leading-[1.05] font-semibold tracking-[-0.035em] text-balance sm:text-[3.25rem]">
          Can AI shoppers buy from your store?
        </h1>
        <p className="mt-5 max-w-xl text-lg text-muted-foreground">
          Paste your store's link. We shop it the way an AI assistant would and tell you what to fix.
        </p>

        <form onSubmit={submit} className="mt-10" noValidate>
          <label htmlFor="store-url" className="text-sm font-medium">
            Your store's web address
          </label>
          <div className="mt-2 flex flex-col gap-2 sm:flex-row sm:gap-0">
            <Input
              id="store-url"
              type="url"
              inputMode="url"
              autoComplete="url"
              placeholder="myshop.com"
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              aria-invalid={!!error}
              aria-describedby={error ? "store-url-error" : undefined}
              className="h-12 border-line text-base shadow-none sm:border-r-0"
            />
            <Button type="submit" disabled={busy} className="h-12 px-6 text-base">
              {busy ? "Starting…" : "Check my store"}
              {!busy && <ArrowRight aria-hidden />}
            </Button>
          </div>
          {error && (
            <p id="store-url-error" role="alert" className="mt-3 text-sm text-bad">
              {error}
            </p>
          )}
        </form>

        <div className="mt-6 text-sm">
          <div>
            <label htmlFor="spending-limit" className="font-medium">
              Spending limit for the demo purchase <span className="font-normal text-muted-foreground">(optional)</span>
            </label>
            <div className="mt-1 flex items-center gap-2">
              <span className="text-muted-foreground" aria-hidden>
                $
              </span>
              <Input
                id="spending-limit"
                inputMode="decimal"
                autoComplete="off"
                placeholder="30.00"
                value={budget}
                onChange={(e) => setBudget(e.target.value)}
                aria-invalid={!!budgetError}
                aria-describedby="spending-limit-help"
                className="h-10 w-28 border-line shadow-none"
              />
            </div>
            <p id="spending-limit-help" role={budgetError ? "alert" : undefined} className={budgetError ? "mt-1 text-bad" : "mt-1 text-[13px] text-muted-foreground"}>
              {budgetError ?? "The shopper won't pay if the checkout total is above this. The demo mug costs $24.00."}
            </p>
          </div>
        </div>

        <div className="mt-3 flex flex-col gap-3 text-sm sm:flex-row sm:items-center sm:gap-6">
          <button
            type="button"
            onClick={() => start(null)}
            disabled={busy}
            className="min-h-11 self-start font-medium underline decoration-line underline-offset-4 hover:decoration-foreground sm:self-auto"
          >
            Or try our demo store
          </button>
          <p className="flex items-center gap-2 text-muted-foreground">
            <ShieldCheck className="size-4 shrink-0" aria-hidden />
            On your store we never buy anything or log in.
          </p>
        </div>
      </div>

      <section aria-labelledby="what-we-check" className="mt-16 border-t-[1.5px] border-rule sm:mt-24">
        <h2 id="what-we-check" className="sr-only">
          What the shopper checks
        </h2>
        <ol className="grid sm:grid-cols-2 lg:grid-cols-4">
          {CHECKS.map(([q, a], i) => (
            <li key={q} className="border-b py-5 sm:pr-6 lg:border-b-0 lg:border-l lg:py-6 lg:pl-6 lg:first:border-l-0 lg:first:pl-0">
              <span className="num text-[13px] text-muted-foreground">{i + 1}</span>
              <p className="mt-2 font-medium">{q}</p>
              <p className="mt-1 text-sm text-muted-foreground">{a}</p>
            </li>
          ))}
        </ol>
      </section>
    </div>
  );
}
