import { ArrowRight, ShieldCheck } from "lucide-react";
import { useState, type FormEvent } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { startCheck } from "@/lib/api";
import { go } from "@/lib/hooks";

export function Home() {
  const [url, setUrl] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const start = async (storeUrl: string | null) => {
    setBusy(true);
    setError(null);
    try {
      const { run_id } = await startCheck(storeUrl);
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
    <div className="mx-auto flex max-w-xl flex-col items-center pt-10 text-center sm:pt-24">
      <h1 className="text-3xl font-semibold tracking-tight text-balance sm:text-5xl">Can AI shoppers buy from your store?</h1>
      <p className="mt-4 text-lg text-muted-foreground">Paste your store's link. We'll shop it like an AI assistant would and tell you what to fix.</p>

      <form onSubmit={submit} className="mt-10 flex w-full flex-col gap-3 text-left" noValidate>
        <label htmlFor="store-url" className="text-sm font-medium">
          Your store's web address
        </label>
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
          className="h-12 bg-card text-base"
        />
        {error && (
          <p id="store-url-error" role="alert" className="text-sm text-bad">
            {error}
          </p>
        )}
        <Button type="submit" disabled={busy} className="h-12 text-base">
          {busy ? "Starting…" : "Check my store"}
          {!busy && <ArrowRight aria-hidden />}
        </Button>
      </form>

      <button
        type="button"
        onClick={() => start(null)}
        disabled={busy}
        className="mt-5 min-h-11 text-sm text-muted-foreground underline underline-offset-4 hover:text-foreground"
      >
        Or try our demo store
      </button>

      <p className="mt-10 flex items-center gap-2 text-sm text-muted-foreground">
        <ShieldCheck className="size-4 shrink-0" aria-hidden />
        We look around like a shopper. On your store we never buy anything or log in.
      </p>
    </div>
  );
}
