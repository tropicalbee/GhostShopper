import { ArrowRight, Bot, CreditCard, FlaskConical, Globe, Plug, Store } from "lucide-react";
import { useState, type FormEvent, type ReactNode } from "react";

import { Logo } from "@/components/bits";
import { Button } from "@/components/ui/button";
import { api, DEMO_PRODUCT, startCheck, storeApi, type FlawState } from "@/lib/api";
import { go, useFetch } from "@/lib/hooks";
import { cn } from "@/lib/utils";

// The API gives the problems as keys and on/off only; the words are ours.
const FLAW_COPY: Record<string, [string, string]> = {
  price_as_image: ["Price only in an image", "The agent can't read the price."],
  no_structured_data: ["Missing product data", "No structured data for the product."],
  ambiguous_buttons: ["Ambiguous buy buttons", "Several look like Buy; only one checks out."],
  extra_checkout_step: ["Extra checkout step", "A details form before payment."],
  never_marks_paid: ["Never marks the order paid", "PayPal captures, the order stays unpaid."],
  declined_marked_paid: ["Declined payment marked paid", "PayPal declines, the store says thanks."],
  success_after_cancel: ["Success after a cancel", "The buyer cancels, the store says thanks."],
  duplicate_on_retry: ["Duplicate order on retry", "A second attempt makes a second order."],
  hidden_agent_instructions: ["Hidden instructions for AI agents", "A review carries a line only agents can read."],
};

const GROUPS: [string, string[]][] = [
  ["WHERE THE AGENT GETS STUCK", ["price_as_image", "no_structured_data", "ambiguous_buttons", "extra_checkout_step"]],
  ["WHERE THE PURCHASE BREAKS", ["never_marks_paid", "declined_marked_paid", "success_after_cancel", "duplicate_on_retry"]],
  ["SAFETY", ["hidden_agent_instructions"]],
];

const STEPS = [
  ["Finds the product", "From the home page, like a real agent"],
  ["Reads price and details", "As text and structured data"],
  ["Checks out", "As a guest, with test details"],
  ["Pays with PayPal", "Practice or sandbox, never real money"],
  ["Reads the order back", "What your store says afterwards"],
];

const RECEIPT = ["01 AGENT WANTED", "02 STORE ORDER", "03 PAYPAL ORDER", "04 PAYPAL CAPTURE", "05 STORE SAYS"];

function Field({ title, help, aside, last, children }: { title: string; help?: ReactNode; aside?: ReactNode; last?: boolean; children?: ReactNode }) {
  return (
    <div className={cn("relative px-6 py-[22px]", !last && "border-b")}>
      <div className="flex items-baseline justify-between gap-3 text-sm font-medium tracking-[-0.01em]">
        <span>{title}</span>
        {aside}
      </div>
      {help && <p className="mt-[3px] text-[13px] text-faint">{help}</p>}
      {children}
    </div>
  );
}

function Option({ on, onClick, icon, title, children }: { on: boolean; onClick: () => void; icon: ReactNode; title: string; children: ReactNode }) {
  return (
    <button
      type="button"
      role="radio"
      aria-checked={on}
      onClick={onClick}
      className={cn(
        "relative flex min-h-11 items-start gap-3 rounded-xl border px-4 py-3.5 text-left transition-colors",
        on ? "border-transparent [background:linear-gradient(180deg,#151515,#0a0a0a)_padding-box,linear-gradient(180deg,rgba(255,255,255,.5),rgba(255,255,255,.12))_border-box]" : "border-[#262626] bg-[#080808] hover:border-[#3a3a3a]",
      )}
    >
      <span className={cn("mt-0.5 grid size-4 flex-none place-items-center rounded-full border-[1.5px]", on ? "border-foreground" : "border-[#4a4a4a]")}>{on && <span className="size-[7px] rounded-full bg-foreground" />}</span>
      <span>
        <b className="block text-sm font-medium">{title}</b>
        <span className="mt-[3px] block text-[12.5px] leading-[18px] text-faint">{children}</span>
      </span>
      <span className="absolute top-3.5 right-3.5 text-dim [&_svg]:size-4">{icon}</span>
    </button>
  );
}

function Switch({ on, disabled, label, onChange }: { on: boolean; disabled: boolean; label: string; onChange: (v: boolean) => void }) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={on}
      aria-label={label}
      disabled={disabled}
      onClick={() => onChange(!on)}
      className={cn("relative h-5 w-[34px] flex-none rounded-full transition-colors disabled:opacity-50", on ? "bg-foreground" : "bg-[#262626]")}
    >
      <span className={cn("absolute top-0.5 left-0.5 size-4 rounded-full transition-transform", on ? "translate-x-3.5 bg-black" : "bg-[#8a8a8a]")} />
    </button>
  );
}

export function NewCheck({ yours }: { yours: boolean }) {
  const [mode, setMode] = useState<"demo" | "live">(yours ? "live" : "demo");
  const [url, setUrl] = useState("");
  const [urlError, setUrlError] = useState<string | null>(null);
  const [budget, setBudget] = useState("");
  const [budgetError, setBudgetError] = useState<string | null>(null);
  const [realChoice, setReal] = useState<boolean | null>(null);
  // Browser agent (reads the store's pages) or the store's WebMCP tools; the tools can also be PayPal's own showcase.
  const [shopper, setShopper] = useState<"browser" | "webmcp">("browser");
  const [mcpStore, setMcpStore] = useState<"demo" | "paypal_showcase">("demo");
  const [vision, setVision] = useState(false);
  const showcase = mode === "demo" && shopper === "webmcp" && mcpStore === "paypal_showcase";
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const health = useFetch(api.health, []).data;
  const flaws = useFetch(storeApi.flaws, []);
  const [state, setState] = useState<FlawState | null>(null);
  const [flawError, setFlawError] = useState<string | null>(null);
  const current = state ?? flaws.data;
  const canEdit = !!health?.presenter_unlocked;
  // The real sandbox is the default whenever the server can run it; the visitor can switch to practice.
  const real = realChoice ?? !!health?.real_checkout_available;

  const keys = GROUPS.flatMap(([, ks]) => ks).filter((k) => current && k in current);
  const on = keys.filter((k) => current?.[k]).length;

  const save = async (next: FlawState) => {
    setFlawError(null);
    try {
      setState(await storeApi.setFlaws(next));
    } catch (e) {
      setFlawError((e as Error).message);
    }
  };

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    let storeUrl: string | null = null;
    if (mode === "live") {
      const value = url.trim();
      if (!value) {
        setUrlError("Type your store's web address first, for example myshop.com");
        return;
      }
      storeUrl = /^https?:\/\//i.test(value) ? value : `https://${value}`;
    } else {
      const limit = budget.trim().replace(/^\$/, "");
      if (limit && !(/^\d{1,5}(\.\d{1,2})?$/.test(limit) && Number(limit) > 0)) {
        setBudgetError("Type an amount in dollars above 0, like 30 or 24.50, or leave it empty.");
        return;
      }
    }
    setUrlError(null);
    setBudgetError(null);
    setBusy(true);
    try {
      const webmcp = !storeUrl && shopper === "webmcp" ? { store: mcpStore } : undefined;
      const { run_id } = await startCheck(storeUrl, storeUrl ? null : budget.trim().replace(/^\$/, ""), !storeUrl && real && !showcase, webmcp, !webmcp && vision);
      go(`/run/${run_id}`);
    } catch (err) {
      const message = (err as Error).message;
      if (storeUrl) setUrlError(message);
      else setError(message);
      setBusy(false);
    }
  };

  const modeLabel = health?.paypal_mode === "mock" ? "Practice (mock PayPal)" : "PayPal sandbox";

  return (
    <div>
      <div className="reveal-in">
        <h1 className="text-2xl leading-[1.15] font-medium tracking-[-0.035em] sm:text-[30px]">New check</h1>
        <p className="mt-2 max-w-[620px] text-[15px] leading-[23px] text-muted-foreground">Send the shopper to a store. It finds a product, checks out, pays with PayPal and reads the order back.</p>
      </div>
      <div className="mt-[26px] grid items-start gap-5 lg:grid-cols-[1fr_360px]">
        <form onSubmit={submit} noValidate className="glass reveal-in overflow-hidden">
          <Field title="Store">
            <div role="radiogroup" aria-label="Store" className="mt-3.5 grid gap-3 sm:grid-cols-2">
              <Option on={mode === "demo"} onClick={() => setMode("demo")} icon={<Store />} title="Demo store">
                Fernhill Ceramics, with problems you can switch on and off.
              </Option>
              <Option on={mode === "live"} onClick={() => setMode("live")} icon={<Globe />} title="Your store">
                Paste a link. Live stores are browsed, never paid.
              </Option>
            </div>
          </Field>

          {mode === "demo" && (
            <Field title="Shopper path" help="The same shopping task, done two ways. Both end at PayPal's checkout and the same purchase trace.">
              <div role="radiogroup" aria-label="Shopper path" className="mt-3.5 grid gap-3 sm:grid-cols-2">
                <Option on={shopper === "browser"} onClick={() => setShopper("browser")} icon={<Bot />} title="Browser agent">
                  Reads the store&apos;s pages and clicks, like a person would. Gets a readiness score.
                </Option>
                <Option on={shopper === "webmcp"} onClick={() => setShopper("webmcp")} icon={<Plug />} title="PayPal WebMCP tools">
                  Uses the store&apos;s own shopping tools: search, product, checkout. No readiness score.
                </Option>
              </div>
              {shopper === "webmcp" && (
                <div role="radiogroup" aria-label="WebMCP store" className="mt-3 grid gap-3 sm:grid-cols-2">
                  <Option on={mcpStore === "demo"} onClick={() => setMcpStore("demo")} icon={<Store />} title="Fernhill's tools">
                    Our adapter on the demo store, with its store problems.
                  </Option>
                  <Option on={mcpStore === "paypal_showcase"} onClick={() => setMcpStore("paypal_showcase")} icon={<Globe />} title="PayPal's showcase">
                    PayPal&apos;s own WebMCP demo store. An external demo, paid in the PayPal sandbox.
                  </Option>
                </div>
              )}
              {shopper === "browser" && health?.vision_available && (
                <div className="mt-4 flex items-center gap-3.5">
                  <div className="flex-1">
                    <b className="block text-[13.5px] font-medium">Shopper can see images</b>
                    <span className="mt-px block text-[12.5px] text-[#8a8a8a]">Uses a vision model to read the page, like a vision-capable AI agent. Slower; does not change the score.</span>
                  </div>
                  <Switch on={vision} disabled={busy} label="Shopper can see images" onChange={setVision} />
                </div>
              )}
            </Field>
          )}

          {mode === "live" ? (
            <>
              <Field title="Store link" help="The home page or any product page. We read robots.txt and go slowly.">
                <div className="mt-3 flex h-[46px] items-center gap-2.5 rounded-[10px] border border-[#2e2e2e] bg-[#080808] px-3.5 transition-[border-color,box-shadow] focus-within:border-[#6a6a6a] focus-within:shadow-[0_0_0_3px_rgba(255,255,255,0.06)]">
                  <Globe className="size-4 text-faint" aria-hidden />
                  <input
                    type="url"
                    inputMode="url"
                    autoComplete="url"
                    placeholder="https://your-store.com"
                    aria-label="Store link"
                    aria-invalid={!!urlError}
                    aria-describedby={urlError ? "url-error" : undefined}
                    value={url}
                    onChange={(e) => setUrl(e.target.value)}
                    className="min-w-0 flex-1 bg-transparent text-sm outline-none placeholder:text-dim"
                  />
                </div>
                {urlError && (
                  <p id="url-error" role="alert" className="mt-2.5 text-[13px] text-bad">
                    {urlError}
                  </p>
                )}
              </Field>
              <Field title="What happens" last>
                <p className="mt-3.5 flex items-start gap-2.5 rounded-[10px] border border-[#1f1f1f] bg-[#0c0c0c] px-3.5 py-3 text-[12.5px] leading-[18px] text-muted-foreground">
                  <CreditCard className="mt-px size-4 flex-none text-faint" aria-hidden />
                  On live stores the shopper finds a product, reaches checkout, but never pays. Payment checks show as not tested.
                </p>
              </Field>
            </>
          ) : showcase ? (
            <Field title="PayPal's showcase" last help="Externally demonstrated on PayPal's own WebMCP showcase. Not GhostShopper-integrated: PayPal's merchant, PayPal's tools.">
              <p className="mt-3.5 flex items-start gap-2.5 rounded-[10px] border border-[#1f1f1f] bg-[#0c0c0c] px-3.5 py-3 text-[12.5px] leading-[18px] text-muted-foreground">
                <CreditCard className="mt-px size-4 flex-none text-faint" aria-hidden />
                The shopper buys a gift card in the PayPal sandbox. Order values come from the tool responses, so there is no store order to compare. This needs a Kernel browser and the sandbox buyer on the server.
              </p>
            </Field>
          ) : (
            <>
              <Field title="Product" help="Every demo check buys the same product, so before and after compare like for like.">
                <div className="mt-3 flex h-12 max-w-[460px] items-center gap-3 rounded-[10px] border border-[#2e2e2e] bg-[#080808] pr-3.5 pl-2">
                  <span className="grid size-8 place-items-center rounded-md bg-gradient-to-br from-[#2a2a2a] to-[#121212]">
                    <Logo className="size-4 text-dim" />
                  </span>
                  <span className="flex-1 text-sm">{DEMO_PRODUCT.name}</span>
                  <span className="num text-[13px] text-faint">{DEMO_PRODUCT.price}</span>
                </div>
              </Field>
              <Field title="Payment" help={health?.paypal_mode === "mock" ? "Practice mode never calls PayPal, and every result says so." : "Uses PayPal's test environment. No real money."}>
                <div role="radiogroup" aria-label="Payment" className="mt-3 grid max-w-full grid-cols-1 gap-[3px] rounded-[10px] border border-[#242424] bg-[#0c0c0c] p-[3px] sm:inline-grid sm:auto-cols-fr sm:grid-flow-col">
                  <button type="button" role="radio" aria-checked={!real} onClick={() => setReal(false)} className={cn("flex min-h-9 items-center justify-center gap-2 rounded-lg px-3.5 text-[13.5px] whitespace-nowrap transition-colors", !real ? "bg-gradient-to-b from-[#1f1f1f] to-[#141414] text-foreground shadow-[inset_0_0_0_1px_#2e2e2e]" : "text-faint")}>
                    <FlaskConical className="size-[15px]" aria-hidden />
                    {modeLabel}
                  </button>
                  {health && (
                    <button type="button" role="radio" aria-checked={real} disabled={!health.real_checkout_available} onClick={() => setReal(true)} className={cn("flex min-h-9 items-center justify-center gap-2 rounded-lg px-3.5 text-[13.5px] whitespace-nowrap transition-colors disabled:opacity-50", real ? "bg-gradient-to-b from-[#1f1f1f] to-[#141414] text-foreground shadow-[inset_0_0_0_1px_#2e2e2e]" : "text-faint")}>
                      <CreditCard className="size-[15px]" aria-hidden />
                      Real PayPal sandbox
                    </button>
                  )}
                </div>
                {health && !health.real_checkout_available && <p className="mt-2 text-[12.5px] text-faint">The real sandbox is not set up on this server (missing {health.real_checkout_missing.join(", ")}).</p>}
                <div className="mt-4 text-[13px]">
                  <label htmlFor="spending-limit" className="font-medium">
                    Spending limit <span className="font-normal text-faint">(optional)</span>
                  </label>
                  <div className="mt-1.5 flex items-center gap-2">
                    <span className="text-faint" aria-hidden>
                      $
                    </span>
                    <input
                      id="spending-limit"
                      inputMode="decimal"
                      autoComplete="off"
                      placeholder="30.00"
                      value={budget}
                      onChange={(e) => setBudget(e.target.value)}
                      aria-invalid={!!budgetError}
                      aria-describedby="spending-limit-help"
                      className="num h-10 w-28 rounded-lg border border-[#2e2e2e] bg-[#080808] px-3 text-sm outline-none focus-visible:border-[#6a6a6a]"
                    />
                  </div>
                  <p id="spending-limit-help" role={budgetError ? "alert" : undefined} className={cn("mt-1.5 text-[12.5px]", budgetError ? "text-bad" : "text-faint")}>
                    {budgetError ?? `The shopper won't pay if the checkout total is above this. The demo product costs ${DEMO_PRODUCT.price}.`}
                  </p>
                </div>
              </Field>
              <Field
                title="Store problems"
                last
                aside={
                  canEdit && current && (
                    <button type="button" onClick={() => save(Object.fromEntries(keys.map((k) => [k, false])))} className="text-[12.5px] font-normal text-muted-foreground hover:text-foreground">
                      Turn all off to test the fixed store
                    </button>
                  )
                }
                help={
                  current
                    ? `Each one is a real problem the shopper should find. ${on} of ${keys.length} are on.${canEdit ? "" : " These settings are locked on this server."}`
                    : flaws.error
                      ? undefined
                      : "Loading the store's settings…"
                }
              >
                {flaws.error && !current && (
                  <p role="alert" className="mt-2 text-[13px] text-bad">
                    {flaws.error}{" "}
                    <button type="button" onClick={flaws.retry} className="underline underline-offset-4">
                      Try again
                    </button>
                  </p>
                )}
                {current && (
                  <div className="mt-3.5 overflow-hidden rounded-xl border border-[#1f1f1f] bg-[#070707]">
                    {GROUPS.map(([group, groupKeys]) => {
                      const shown = groupKeys.filter((k) => k in current);
                      return shown.length === 0 ? null : (
                        <div key={group}>
                          <div className="num border-b border-[#1a1a1a] bg-[#0c0c0c] px-4 py-[9px] text-[11px] leading-4 font-medium tracking-[0.08em] text-dim">{group}</div>
                          {shown.map((k) => (
                            <div key={k} className="flex items-center gap-3.5 border-b border-[#161616] px-4 py-3 last:border-b-0 hover:bg-[#0c0c0c]">
                              <div className="flex-1">
                                <b className="block text-[13.5px] font-medium">{FLAW_COPY[k][0]}</b>
                                <span className="mt-px block text-[12.5px] text-[#8a8a8a]">{FLAW_COPY[k][1]}</span>
                              </div>
                              <Switch on={current[k]} disabled={!canEdit} label={FLAW_COPY[k][0]} onChange={(v) => save({ [k]: v })} />
                            </div>
                          ))}
                        </div>
                      );
                    })}
                  </div>
                )}
                {flawError && (
                  <p role="alert" className="mt-2.5 text-[13px] text-bad">
                    {flawError}
                  </p>
                )}
              </Field>
            </>
          )}

          <div className="flex flex-wrap items-center gap-4 rounded-b-[14px] bg-gradient-to-r from-[#0f0f0f] to-[#070707] px-6 py-[18px]">
            <Button type="submit" disabled={busy} className="shine h-11 rounded-[10px] px-5 text-[14.5px]">
              {busy ? "Starting…" : "Start check"}
              {!busy && <ArrowRight aria-hidden />}
            </Button>
            <span className="text-[13px] text-faint">Takes 10 to 40 seconds. You can watch every step.</span>
            {error && (
              <p role="alert" className="w-full text-[13px] text-bad">
                {error}
              </p>
            )}
          </div>
        </form>

        <aside className="grid gap-5">
          <section className="glass reveal-in">
            <div className="panel-head">
              <div>
                <h3 className="text-[15px] font-medium tracking-[-0.02em]">What the shopper does</h3>
                <p className="mt-0.5 text-[13px] text-faint">The same five stages as the trace.</p>
              </div>
            </div>
            <ol className="relative px-5 pt-2 pb-[18px] before:absolute before:top-6 before:bottom-[30px] before:left-[31px] before:w-[1.5px] before:bg-[linear-gradient(#333_50%,transparent_0)] before:bg-[length:1.5px_8px]">
              {STEPS.map(([t, d], i) => (
                <li key={t} className="relative flex items-start gap-3.5 py-2.5">
                  <span className="num grid size-6 flex-none place-items-center rounded-full border-[1.5px] border-[#3a3a3a] bg-black text-[11px] font-medium text-muted-foreground">{i + 1}</span>
                  <div>
                    <b className="block text-[13.5px] font-medium">{t}</b>
                    <span className="mt-px block text-[12.5px] text-[#8a8a8a]">{d}</span>
                  </div>
                </li>
              ))}
            </ol>
          </section>
          <section className="glass reveal-in">
            <div className="panel-head">
              <div>
                <h3 className="text-[15px] font-medium tracking-[-0.02em]">Your receipt</h3>
                <p className="mt-0.5 text-[13px] text-faint">Prints as the shopper goes.</p>
              </div>
            </div>
            <div className="paper mx-auto mt-[18px] mb-[22px] w-[250px] max-w-[calc(100%-32px)] -rotate-[1.2deg] px-4 pt-[18px] pb-3.5 text-[10.5px] leading-4 shadow-[0_20px_40px_rgba(0,0,0,0.6)]">
              <div className="text-center font-medium tracking-[0.12em]">
                <Logo className="mx-auto mb-[3px] size-[18px]" />
                PURCHASE TRACE
              </div>
              <div className="dash" />
              {RECEIPT.map((r) => (
                <div key={r} className="flex justify-between">
                  <span>{r}</span>
                  <span className="tracking-[0.1em] text-[#999]">· · ·</span>
                </div>
              ))}
              <div className="dash" />
              <div className="flex justify-between">
                <span>READINESS</span>
                <span className="tracking-[0.1em] text-[#999]">· · ·</span>
              </div>
              <div className="tear" />
            </div>
          </section>
        </aside>
      </div>
    </div>
  );
}
