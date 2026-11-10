import { ArrowRight, Camera, Check, CreditCard, Crosshair, Globe, Image as ImageIcon, MousePointer2, MousePointerClick, ReceiptText, ScanEye, Store, Timer, X } from "lucide-react";
import { useEffect, useRef, useState, type CSSProperties, type FormEvent, type ReactNode } from "react";

import { Logo } from "@/components/bits";
import { ScoreRing, type RingMark } from "@/components/ReadinessPanels";
import { TraceTable } from "@/components/TraceTable";
import { startCheck, type Trace, type TraceCell } from "@/lib/api";
import { go, useCountUp } from "@/lib/hooks";
import { cn } from "@/lib/utils";

// Everything on this page is an illustration of one made-up practice run. It never comes from the API.

const known = (value: string | number): TraceCell => ({ kind: "known", value, reason: null });
const unknown = (reason: string): TraceCell => ({ kind: "unknown", value: null, reason });
const na = (reason: string): TraceCell => ({ kind: "n/a", value: null, reason });
const noItems = unknown("store sent no item list");
const noCaptureItems = na("captures carry no items");

const SAMPLE: Trace = {
  stages: [
    { key: "agent_wanted", label: "", source: "intent, step 6", cells: { product: known("Speckled Stoneware Mug"), quantity: known(1), amount: known("24.00"), currency: known("USD"), status: known("Buy 1") }, evidence: {} },
    { key: "store_order", label: "", source: "#1042", cells: { product: known("Speckled Stoneware Mug"), quantity: known(1), amount: known("24.00"), currency: known("USD"), status: known("Created") }, evidence: {} },
    { key: "paypal_order", label: "", source: "5O190127TN364715T", cells: { product: noItems, quantity: noItems, amount: known("24.00"), currency: known("USD"), status: known("COMPLETED") }, evidence: {} },
    { key: "paypal_capture", label: "", source: "3C679366HH908993F", cells: { product: noCaptureItems, quantity: noCaptureItems, amount: known("24.00"), currency: known("USD"), status: known("COMPLETED") }, evidence: {} },
    { key: "store_says", label: "", source: "order page, step 14", cells: { product: known("Speckled Stoneware Mug"), quantity: known(1), amount: known("24.00"), currency: known("USD"), status: known("Awaiting payment") }, evidence: {} },
  ],
  mismatches: [],
  first_mismatch: {
    stage: "store_says",
    field: "status",
    expected: "paid",
    actual: "Awaiting payment",
    explanation: "PayPal captured $24.00, but your store still says Awaiting payment.",
    fix: "Mark order #1042 paid when the capture call returns COMPLETED, or handle the PAYMENT.CAPTURE.COMPLETED webhook.",
    first: true,
  },
  counts: { mismatch: 1, unknown: 2 },
};

const FAILED = new Set([2, 7, 11, 15]);
const MARKS = (after: boolean): RingMark[] => Array.from({ length: 18 }, (_, i) => (!after && FAILED.has(i) ? "fail" : "pass"));

const wrap = "mx-auto w-[min(1240px,100%-32px)] sm:w-[min(1240px,100%-64px)]";
const h2 = "text-[clamp(32px,3.1vw,44px)] leading-[1.06] font-medium tracking-[-0.04em]";
const lede = "mt-3.5 max-w-[580px] text-[17px] leading-[27px] text-muted-foreground";

const btn = "relative inline-flex h-11 items-center gap-2 overflow-hidden rounded-full border border-transparent px-5 text-[15px] font-medium tracking-[-0.01em] whitespace-nowrap no-underline transition-colors [&_svg]:size-4 [&_svg]:transition-transform hover:[&_svg]:translate-x-[3px]";
const white = cn(btn, "shine bg-foreground text-[#0a0a0a]");
const dark = cn(btn, "border-[#2e2e2e] bg-card text-foreground hover:border-[#555] hover:bg-[#111]");

function Chip({ children, on }: { children: ReactNode; on?: boolean }) {
  return <span className={cn("inline-flex items-center gap-1.5 rounded-full border px-2.5 py-[3px] text-xs leading-4 font-medium whitespace-nowrap", on ? "border-[#2e2e2e] bg-[#1a1a1a] text-foreground" : "border-[#262626] bg-[#141414] text-muted-foreground")}>{children}</span>;
}

const TRACE_STEPS = [
  ["agent_wanted", "Agent wanted", "What the shopper meant to buy"],
  ["store_order", "Store order", "What your store recorded"],
  ["paypal_order", "PayPal order", "What PayPal was asked to charge"],
  ["paypal_capture", "PayPal capture", "What PayPal actually took"],
  ["store_says", "Store says", "What your store shows afterwards"],
] as const;
// The lit dot is the stage of the first mismatch.
const LIT_STEP = Math.max(0, TRACE_STEPS.findIndex(([key]) => key === SAMPLE.first_mismatch?.stage));

// The ghost shopper (the logo) strolls the stepper once, from the first dot to the lit one, when it scrolls into view.
// Desktop only: below md the stepper is a vertical list with no line.
function TraceGhost({ count, target }: { count: number; target: number }) {
  const ref = useRef<HTMLDivElement>(null);
  const bodyRef = useRef<HTMLDivElement>(null);
  // Column i starts at i * (100% / count) with its 22px dot; the ghost's body centre is 13px into the 34px mark, so
  // shifting by -2px puts the body over the dot centre (11px).
  const leftAt = (i: number) => `calc(${(i * 100) / count}% - 2px)`;

  useEffect(() => {
    const el = ref.current;
    const body = bodyRef.current;
    const host = el?.parentElement;
    if (!el || !body || !host) return;
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches || typeof IntersectionObserver === "undefined") {
      el.style.left = leftAt(target);
      return;
    }
    // A slow, even stroll: about 1.25 s per stage, easing gently in and out, with a slight lean on the way.
    const timing = { duration: Math.max(1600, target * 1250), delay: 200, fill: "forwards" as const };
    const io = new IntersectionObserver(
      (entries) => {
        if (!entries.some((e) => e.isIntersecting)) return;
        io.disconnect();
        if (target === 0) return;
        const walk = el.animate([{ left: leftAt(0) }, { left: leftAt(target) }], { ...timing, easing: "cubic-bezier(0.45, 0, 0.55, 1)" });
        walk.addEventListener("finish", () => (el.style.left = leftAt(target)));
        body.animate(
          [
            { transform: "rotate(0deg)", offset: 0 },
            { transform: "rotate(4deg)", offset: 0.15 },
            { transform: "rotate(4deg)", offset: 0.85 },
            { transform: "rotate(0deg)", offset: 1 },
          ],
          { ...timing, easing: "ease-in-out" },
        );
      },
      { threshold: 0.5 },
    );
    io.observe(host);
    return () => io.disconnect();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [count, target]);

  return (
    <div ref={ref} className="pointer-events-none absolute top-[4px] left-0 hidden size-[34px] text-foreground md:block" aria-hidden>
      <div ref={bodyRef} className="size-full" style={{ transformOrigin: "40% 90%" }}>
        <Logo className="size-full" />
      </div>
    </div>
  );
}

function Node({ hit, className }: { hit?: boolean; className?: string }) {
  return (
    <span className={cn("grid size-[22px] place-items-center rounded-full border-[1.5px]", hit ? "border-foreground bg-foreground" : "border-[#4a4a4a] bg-black", className)}>
      <span className={cn("size-1.5 rounded-full", hit ? "bg-black" : "bg-muted-foreground")} />
    </span>
  );
}

function Spine({ tag, hit, top, children }: { tag: string; hit?: boolean; top?: number; children: ReactNode }) {
  return (
    <section>
      <div className={cn(wrap, "md:grid md:grid-cols-[84px_1fr]")}>
        <div className="relative hidden md:block">
          <div className="absolute top-0 bottom-0 left-2.5 w-0.5 bg-[linear-gradient(#2e2e2e_50%,transparent_0)] bg-[length:2px_10px]" aria-hidden />
          <Node hit={hit} className="sticky top-[110px] mt-[118px]" />
          <div className="absolute top-40 left-[3px] [writing-mode:vertical-rl] rotate-180 font-mono text-[11px] leading-4 font-medium tracking-[0.08em] text-faint">{tag}</div>
        </div>
        <div className="min-w-0 pb-[90px]" style={{ paddingTop: top ?? 110 }}>
          {children}
        </div>
      </div>
    </section>
  );
}

const jump = (id: string) => document.getElementById(id)?.scrollIntoView({ behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth" });

export function Landing() {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [url, setUrl] = useState("");
  const [after, setAfter] = useState(false);
  const [touched, setTouched] = useState(false);
  const [ctaInView, setCtaInView] = useState(false);
  const navCtas = useRef<HTMLDivElement>(null);
  const score = useCountUp(after ? 100 : 62, touched ? (after ? 62 : 100) : 0, 1100);

  // The header CTAs duplicate the in-page ones, so hide them while a [data-cta] section is on screen.
  useEffect(() => {
    const seen = new Set<Element>();
    const io = new IntersectionObserver(
      (entries) => {
        for (const e of entries) {
          if (e.isIntersecting) seen.add(e.target);
          else seen.delete(e.target);
        }
        setCtaInView(seen.size > 0);
      },
      { rootMargin: "-64px 0px 0px 0px" }, // the sticky header covers the top 64px
    );
    document.querySelectorAll("[data-cta]").forEach((el) => io.observe(el));
    return () => io.disconnect();
  }, []);
  useEffect(() => {
    navCtas.current?.toggleAttribute("inert", ctaInView);
  }, [ctaInView]);

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
  const paste = (e: FormEvent) => {
    e.preventDefault();
    const value = url.trim();
    if (!value) {
      setError("Type your store's web address first, for example myshop.com");
      return;
    }
    start(/^https?:\/\//i.test(value) ? value : `https://${value}`);
  };
  const toggle = (next: boolean) => {
    setTouched(true);
    setAfter(next);
  };

  return (
    <div className="overflow-x-clip">
      <nav className="sticky top-0 z-50 border-b bg-black/95" aria-label="Main">
        <div className={cn(wrap, "flex h-16 items-center justify-between")}>
          <div className="flex items-center">
            <a href="#/" className="flex items-center gap-[9px] text-base font-semibold tracking-[-0.03em] text-foreground no-underline">
              <Logo className="size-[22px]" />
              GhostShopper
            </a>
            <div className="ml-9 hidden gap-[26px] text-sm text-muted-foreground lg:flex">
              {[
                ["How it works", "how"],
                ["Purchase trace", "trace"],
                ["Readiness score", "score"],
              ].map(([label, id]) => (
                <button key={id} type="button" onClick={() => jump(id)} className="transition-colors hover:text-foreground">
                  {label}
                </button>
              ))}
            </div>
          </div>
          <div ref={navCtas} aria-hidden={ctaInView || undefined} className={cn("flex gap-2 transition-opacity duration-150 motion-reduce:transition-none", ctaInView && "pointer-events-none opacity-0")}>
            <a href="#/new?store=yours" className="inline-flex h-[34px] items-center rounded-md border border-[#2e2e2e] bg-card px-3 text-[13.5px] font-medium whitespace-nowrap text-foreground no-underline hover:border-[#555] max-sm:hidden">
              Check your store
            </a>
            <button type="button" disabled={busy} onClick={() => start(null)} className="shine inline-flex h-[34px] items-center rounded-md bg-foreground px-3 text-[13.5px] font-medium whitespace-nowrap text-[#0a0a0a] disabled:opacity-60">
              Run the demo
            </button>
          </div>
        </div>
      </nav>

      <section data-cta className="relative overflow-hidden pt-16 pb-20 lg:pt-24 lg:pb-[110px]">
        <div className={cn(wrap, "relative grid items-center gap-12 lg:grid-cols-[1fr_430px]")}>
          <div className="reveal-in">
            <h1 className="text-[clamp(40px,4vw,58px)] leading-[1.02] font-medium tracking-[-0.045em] text-balance">See your store through an AI shopper&apos;s eyes.</h1>
            <p className="mt-[22px] max-w-[500px] text-[17px] leading-[27px] text-muted-foreground">An AI agent shops your store and pays with PayPal. GhostShopper then checks that the agent, PayPal and your store agree on what was bought, and shows where they don&apos;t.</p>
            <div className="mt-8 flex flex-wrap gap-2.5">
              <button type="button" disabled={busy} onClick={() => start(null)} className={cn(white, "disabled:opacity-60")}>
                {busy ? "Starting…" : "Run a check on the demo store"}
                {!busy && <ArrowRight aria-hidden />}
              </button>
              <a href="#/new?store=yours" className={dark}>
                Check your own store
              </a>
            </div>
            <p className="mt-4 text-[13px] text-faint">The demo needs no keys. Real runs pay in the PayPal sandbox.</p>
            {error && (
              <p role="alert" className="mt-3 text-sm text-bad">
                {error}
              </p>
            )}
          </div>
          <div className="relative flex flex-col items-center">
            <div className="pointer-events-none absolute top-[46%] left-1/2 size-[620px] max-w-none -translate-x-1/2 -translate-y-1/2 rounded-full opacity-55 blur-[60px] [background:conic-gradient(from_0deg,transparent,rgba(255,255,255,.28)_8%,transparent_20%,rgba(255,255,255,.14)_42%,transparent_55%,rgba(255,255,255,.22)_74%,transparent_86%)] max-sm:size-[360px]" aria-hidden />
            <div className="relative z-[3] h-5 w-[410px] max-w-full rounded-lg border border-[#333] bg-gradient-to-b from-[#202020] to-[#070707] shadow-[inset_0_-6px_10px_rgba(0,0,0,0.9),0_10px_30px_rgba(0,0,0,0.8)]" aria-hidden />
            <div className="paper print-in z-[2] -mt-2 w-[350px] max-w-[calc(100%-24px)] origin-top -rotate-[1.4deg] px-[22px] pt-[26px] pb-5 text-[11.5px] leading-[17.5px] shadow-[0_30px_80px_rgba(255,255,255,0.07),0_20px_50px_rgba(0,0,0,0.6)]" role="img" aria-label="An example purchase trace receipt: four records agree, the store's page says Awaiting payment">
              <div className="text-center">
                <Logo className="mx-auto size-[26px]" />
                <div className="mt-[5px] font-medium tracking-[0.14em]">PURCHASE TRACE</div>
                <div className="text-[#555]">EXAMPLE RUN · PRACTICE MODE</div>
                <div className="text-[#555]">fernhill-ceramics.store</div>
              </div>
              <div className="dash" />
              {(
                [
                  ["01 AGENT WANTED", "Speckled Stoneware Mug", "1 × 24.00"],
                  ["02 STORE ORDER", "#1042", "24.00 USD"],
                  ["03 PAYPAL ORDER", "5O19…715T", "24.00 USD"],
                  ["04 PAYPAL CAPTURE", "3C67…993F COMPLETED", "24.00 USD"],
                ] as const
              ).map(([k, a, b]) => (
                <div key={k} className="mb-[7px]">
                  <div className="flex items-center justify-between gap-2.5">
                    <span className="font-medium">{k}</span>
                    <Check className="size-[13px]" aria-hidden />
                  </div>
                  <div className="flex justify-between gap-2.5 text-[#333]">
                    <span>{a}</span>
                    <span>{b}</span>
                  </div>
                </div>
              ))}
              <div className="-mx-2 mb-[7px] bg-[#111] px-2 py-[5px] text-[#ececec]">
                <div className="flex items-center justify-between gap-2.5">
                  <span className="font-medium">05 STORE SAYS</span>
                  <X className="size-[13px]" aria-hidden />
                </div>
                <div className="flex justify-between gap-2.5">
                  <span>Awaiting payment</span>
                  <span>MISMATCH</span>
                </div>
              </div>
              <div className="dash" />
              <div className="flex justify-between gap-2.5">
                <span className="font-medium">FIRST MISMATCH</span>
                <span>STAGE 05</span>
              </div>
              <div className="mt-[3px] text-[#333]">Fix: mark the order paid when the capture completes.</div>
              <div className="mt-3 mb-[7px] h-8 bg-[repeating-linear-gradient(90deg,#111_0_2px,transparent_2px_4px,#111_4px_5px,transparent_5px_8px,#111_8px_11px,transparent_11px_12px,#111_12px_13px,transparent_13px_16px)]" aria-hidden />
              <div className="text-center text-[10px] tracking-[0.08em] text-[#555]">PRACTICE MODE · MOCK PAYPAL</div>
              <div className="tear" />
            </div>
          </div>
        </div>
      </section>

      <section id="how" className="relative border-y bg-gradient-to-b from-[#060606] to-black">
        <ol className={cn(wrap, "relative grid gap-6 pt-10 pb-9 md:grid-cols-5 md:gap-0")}>
          <div className="march absolute top-[50px] right-[calc(20%-10px)] left-2.5 hidden h-0.5 md:block" aria-hidden />
          <TraceGhost count={TRACE_STEPS.length} target={LIT_STEP} />
          {TRACE_STEPS.map(([key, t, d], i) => (
            <li key={key} className="relative flex gap-3.5 md:block md:pr-5">
              <Node hit={i === LIT_STEP} className="relative z-[1] flex-none" />
              <div>
                <b className="block text-[15px] leading-[22px] font-medium tracking-[-0.02em] md:mt-4">{t}</b>
                <span className="mt-[3px] block text-[13px] leading-[19px] text-faint">{d}</span>
              </div>
            </li>
          ))}
        </ol>
      </section>

      <Spine tag="01 · AGENT WANTED">
        <div className="grid items-start gap-12 xl:grid-cols-[400px_1fr]">
          <div className="reveal-in">
            <h2 className={h2}>An AI shopper walks your store, step by step.</h2>
            <p className={lede}>It reads pages, clicks and pays with real tool calls. Nothing is scripted, so it gets stuck where a real agent would.</p>
            <div className="mt-8 border-t">
              {(
                [
                  [Camera, "A screenshot of what the browser saw"],
                  [Crosshair, "The exact selector it used"],
                  [Timer, "How long every step took"],
                ] as const
              ).map(([I, t]) => (
                <div key={t} className="flex items-center gap-3 border-b py-3.5 text-[15px]">
                  <I className="size-[17px] text-muted-foreground" aria-hidden />
                  {t}
                </div>
              ))}
            </div>
          </div>
          <div className="glass reveal-in overflow-hidden" role="img" aria-label="An example live check: six steps and a screenshot where the price is an image">
            <div className="flex items-center justify-between border-b px-[18px] py-[13px] text-sm text-muted-foreground">
              <span className="flex items-center gap-2.5">
                Live check <Chip>Example · Practice mode</Chip>
              </span>
              <span className="num flex items-center gap-2 text-xs text-faint">
                <span className="size-[7px] rounded-full bg-foreground" />
                00:31
              </span>
            </div>
            <div className="grid sm:grid-cols-[1fr_250px]">
              <div className="grid gap-0.5 px-[18px] py-4">
                {(
                  [
                    [Store, "Opened fernhill-ceramics.store", "00:02"],
                    [ScanEye, "Found the Speckled Stoneware Mug", "00:06"],
                    [ImageIcon, "Price is an image, could not read it", "00:09"],
                    [MousePointerClick, "Clicked Add to cart", "00:14"],
                    [CreditCard, "Paid in the PayPal sandbox", "00:24"],
                    [ReceiptText, "Read order #1042 back", "00:31"],
                  ] as const
                ).map(([I, t, at], i) => (
                  <div key={t} className={cn("grid grid-cols-[20px_1fr_auto] items-center gap-3 rounded-lg px-2.5 py-[9px] text-sm transition-colors hover:bg-[#101010]", i === 2 && "bg-gradient-to-r from-[#161616] to-[#0c0c0c] text-faint shadow-[inset_0_0_0_1px_#2a2a2a]")}>
                    <I className="size-[17px]" aria-hidden />
                    {t}
                    <span className="num text-[11.5px] text-dim">{at}</span>
                  </div>
                ))}
              </div>
              <div className="border-t p-4 sm:border-t-0 sm:border-l">
                <div className="num mb-2.5 flex justify-between text-[10.5px] text-dim">
                  <span>step 3 · screenshot</span>
                  <span>1280×800</span>
                </div>
                <div className="relative h-[270px] overflow-hidden rounded-lg border border-[#262626] bg-[#0b0b0b] p-[11px]">
                  <div className="h-[104px] rounded-md bg-gradient-to-br from-[#1e1e1e] to-[#0f0f0f]" />
                  <div className="mt-[11px] text-[13px] font-medium">Speckled Stoneware Mug</div>
                  <div className="num mt-[9px] grid h-6 w-[78px] place-items-center rounded outline-[1.5px] outline-offset-[3px] outline-foreground [outline-style:dashed] bg-[#1f1f1f] text-[11px] font-medium text-[#666]">$24.00</div>
                  <div className="num absolute top-[132px] right-2.5 rounded-md border border-[#3a3a3a] bg-black px-[7px] py-[5px] text-[10.5px] leading-[14px]">
                    read_text .price
                    <br />→ &quot;&quot; (image)
                  </div>
                  <div className="mt-5 h-7 rounded-md border border-[#2a2a2a] bg-[#1a1a1a]" />
                </div>
              </div>
            </div>
          </div>
        </div>
      </Spine>

      <div id="trace" />
      <Spine tag="02 – 04 · THE MONEY" top={50}>
        <div className="reveal-in">
          <h2 className={h2}>Then it follows the money.</h2>
          <p className={lede}>Your store&apos;s order, PayPal&apos;s order and PayPal&apos;s capture, set next to what the agent meant to buy. Same five fields, read from the source each time.</p>
        </div>
        <div className="glass reveal-in mt-11 overflow-hidden">
          <div className="relative flex flex-wrap items-center justify-between gap-3 border-b px-[18px] py-3 text-[13px] text-faint">
            <span className="flex items-center gap-5">
              <span className="flex items-center gap-[9px] text-sm font-semibold tracking-[-0.03em] text-foreground">
                <Logo className="size-[18px]" />
                GhostShopper
              </span>
              <span className="max-sm:hidden">My checks</span>
              <Chip on>Purchase trace</Chip>
            </span>
            <Chip>Practice mode: mock PayPal</Chip>
          </div>
          <div className="relative flex flex-wrap items-end justify-between gap-3 px-6 pt-[30px] pb-5">
            <div>
              <h3 className="text-[26px] leading-[1.1] font-medium tracking-[-0.04em]">Paid, but your store doesn&apos;t know.</h3>
              <p className="mt-1.5 text-sm text-faint">Example run · fernhill-ceramics.store · practice mode</p>
            </div>
            <Chip>1 mismatch · 2 unknown</Chip>
          </div>
          <div className="pb-6 md:px-6">
            <TraceTable trace={SAMPLE} name={(s) => s} evidence={[]} />
          </div>
        </div>
      </Spine>

      <Spine tag="05 · STORE SAYS" hit top={50}>
        <div className="reveal-in">
          <h2 className={h2}>If your store doesn&apos;t say, neither do we.</h2>
          <p className={lede}>The last record is the one shoppers and agents actually see. When it disagrees, you get the fix. When it&apos;s missing, the trace says Unknown and names what&apos;s missing.</p>
        </div>
        <div className="mt-11 grid gap-[18px] md:grid-cols-2">
          <div className="glass lift reveal-in overflow-hidden p-7">
            <h3 className="text-[21px] leading-[1.2] font-medium tracking-[-0.03em]">When the store says something wrong</h3>
            <p className="mt-2 text-[15px] leading-[23px] text-muted-foreground">The first disagreement is marked. Later ones are left alone, because they usually follow from the first.</p>
            <div className="mt-6 overflow-hidden rounded-[10px] border border-[#1f1f1f] bg-[#070707] text-[13.5px]">
              <div className="grid grid-cols-[130px_1fr] border-b border-[#1a1a1a]">
                <span className="border-r border-[#1a1a1a] p-3 text-faint">PayPal capture</span>
                <span className="num p-3">COMPLETED · 24.00 USD</span>
              </div>
              <div className="grid grid-cols-[130px_1fr] border-b border-[#1a1a1a]">
                <span className="border-r border-[#1a1a1a] p-3 text-faint">Store says</span>
                <span className="p-3 shadow-[inset_0_0_0_1px_#6a6a6a] [background:radial-gradient(120%_140%_at_50%_0%,rgba(255,255,255,.12),rgba(255,255,255,.03))]">Awaiting payment</span>
              </div>
              <div className="grid grid-cols-[130px_1fr]">
                <span className="border-r border-[#1a1a1a] p-3 text-faint">Verdict</span>
                <span className="p-3">
                  <span className="pill-inv">First mismatch</span>
                </span>
              </div>
            </div>
          </div>
          <div className="glass lift reveal-in overflow-hidden p-7">
            <h3 className="text-[21px] leading-[1.2] font-medium tracking-[-0.03em]">When the store says nothing</h3>
            <p className="mt-2 text-[15px] leading-[23px] text-muted-foreground">No order status on the page means Unknown, never a guess. The model doesn&apos;t fill gaps.</p>
            <div className="mt-6 rounded-[10px] border border-[#262626] bg-[#0b0b0b] p-5">
              <div className="text-lg font-semibold tracking-[-0.02em]">Thank you for your order!</div>
              <div className="mt-[5px] text-[13.5px] text-[#8a8a8a]">We&apos;ll email you when it ships.</div>
              <div className="num mt-3.5 flex h-[30px] items-center rounded-md border border-dashed border-[#5a5a5a] px-2.5 text-[11.5px] text-faint">no order status on this page</div>
            </div>
            <div className="mt-3 flex items-center gap-3 text-[13.5px] text-muted-foreground">
              <Chip>Status: Unknown</Chip>thanks page, step 14
            </div>
          </div>
        </div>
      </Spine>

      <section id="score" className="relative overflow-hidden py-24 lg:py-[120px]">
        <div className="pointer-events-none absolute top-[55%] left-1/2 size-[1000px] max-w-none -translate-x-1/2 -translate-y-1/2 [background:radial-gradient(circle,rgba(255,255,255,.06),transparent_62%)]" aria-hidden />
        <div className={cn(wrap, "relative")}>
          <div className="reveal-in flex flex-wrap items-end justify-between gap-x-10 gap-y-4">
            <h2 className={cn(h2, "max-w-[560px]")}>And the score says where it got stuck.</h2>
            <p className="max-w-[440px] text-[17px] leading-[27px] text-muted-foreground">The trace shows what happened to the money. The score shows why the agent struggled. Only problems your store causes cost points.</p>
          </div>
          <div className="glass reveal-in mt-11 overflow-hidden">
            <div className="relative flex flex-wrap items-center justify-between gap-3 border-b px-[18px] py-3 text-[13px] text-faint">
              <span className="flex items-center gap-5">
                <span className="flex items-center gap-[9px] text-sm font-semibold tracking-[-0.03em] text-foreground">
                  <Logo className="size-[18px]" />
                  GhostShopper
                </span>
                <Chip on>Readiness score</Chip>
              </span>
              <Chip>Example · Practice mode</Chip>
            </div>
            <div className="grid min-h-[430px] lg:grid-cols-[400px_1fr]">
              <div className="relative grid place-items-center border-b p-[30px] lg:border-r lg:border-b-0 [background:radial-gradient(circle_at_50%_50%,rgba(255,255,255,.05),transparent_60%)]">
                <ScoreRing marks={MARKS(after)} size={300} stroke={14} className="size-[240px] sm:size-[290px]" />
                <div className="absolute text-center">
                  <div className="num text-[76px] leading-none font-medium tracking-[-0.06em]">{score}</div>
                  <div className="mt-1 text-[15px] text-dim">out of 100</div>
                  <div className="mt-2.5 text-[12.5px] text-faint">{after ? "18 of 18" : "14 of 18"} checks passed</div>
                </div>
              </div>
              <div className="num flex flex-col px-[18px] py-[30px] text-[13.5px] sm:px-[34px]">
                <div className="mb-[18px] flex items-center justify-between gap-3 font-sans">
                  <span className="text-sm text-muted-foreground">How the score adds up</span>
                  <span role="group" aria-label="Before or after fixes" className="inline-flex rounded-full border border-[#262626] bg-[#111] p-[3px]">
                    {(
                      [
                        ["Before fixes", false],
                        ["After fixes", true],
                      ] as const
                    ).map(([label, v]) => (
                      <button key={label} type="button" aria-pressed={after === v} onClick={() => toggle(v)} className={cn("min-h-8 rounded-full px-3.5 text-[12.5px] leading-4 font-medium transition-colors", after === v ? "bg-foreground text-black" : "text-faint")}>
                        {label}
                      </button>
                    ))}
                  </span>
                </div>
                <Line op="" label="Starting score" v="100" />
                <Line op="−" label="Price only in an image" hint="Put the price in the page as text." v="15" gone={after} />
                <Line op="−" label="Order never marked paid" hint="Mark the order paid when the capture completes." v="13" gone={after} />
                <Line op="−" label="No product data" hint="Add Product structured data (JSON-LD)." v="10" gone={after} />
                <Line op="·" label="Not your store's fault" hint="Nothing in this example. A declined card would be listed here, at no cost." v="0" dim />
                <div className="mt-1.5 grid grid-cols-[22px_1fr_auto] gap-2.5 border-t-[1.5px] border-[#3a3a3a] pt-3.5 text-[15px] font-medium">
                  <span className="text-dim">=</span>
                  <span>Readiness score</span>
                  <span className="text-right">{score}</span>
                </div>
              </div>
            </div>
            <div className="flex items-center gap-2.5 border-t bg-gradient-to-r from-[#0d0d0d] to-[#060606] px-6 py-3.5 text-[12.5px] text-faint">
              <Check className="size-[15px] flex-none" aria-hidden />
              Every check keeps its screenshot. No points come from the model.
            </div>
          </div>
        </div>
      </section>

      <section className="pt-8 pb-[120px]">
        <div className={wrap}>
          <div className="reveal-in">
            <h2 className={h2}>What it catches.</h2>
            <p className="mt-3.5 max-w-[600px] text-[17px] leading-[27px] text-muted-foreground">Each one is a real problem planted in the demo store. Switch them on, run the check, and watch the shopper find them.</p>
          </div>
          <div className="mt-11 grid auto-rows-[310px] gap-[18px] sm:grid-cols-2 lg:grid-cols-3">
            <Catch wide title="No product data" text="People see a mug and a price. An agent looks for structured product data and finds none, so it can't confirm what it's buying.">
              <div className="relative w-[min(520px,90%)] overflow-hidden rounded-[10px] border border-[#262626] bg-gradient-to-b from-[#0d0d0d] to-[#060606] font-mono text-[12.5px] leading-[21px]" aria-hidden>
                <div className="pointer-events-none absolute right-0 left-0 z-[1] h-[22px] border-b border-white/30 bg-gradient-to-b from-transparent to-white/10" style={{ animation: "scan 2.6s var(--ease) infinite" } as CSSProperties} />
                <div className="flex justify-between border-b border-[#1c1c1c] px-3 py-2 text-[11px] text-dim">
                  <span>/products/speckled-stoneware-mug</span>
                  <span>view source</span>
                </div>
                <pre className="py-2.5 text-faint">
                  {[
                    ['<div class="product">', false],
                    ["  <h1>Speckled Stoneware Mug</h1>", false],
                    ['  <img src="price-24.png">', false],
                    ['  <script type="application/ld+json">  not found', true],
                    ["</div>", false],
                  ].map(([t, miss], i) => (
                    <div key={i} className={cn("grid grid-cols-[34px_1fr] px-3", miss && "mx-2.5 rounded-[5px] px-1.5 text-foreground shadow-[inset_0_0_0_1px_#6a6a6a] [background:radial-gradient(120%_160%_at_50%_0%,rgba(255,255,255,.12),rgba(255,255,255,.03))]")}>
                      <i className="text-[#3d3d3d] not-italic">{41 + i}</i>
                      <span className="overflow-hidden text-ellipsis whitespace-pre">{t as string}</span>
                    </div>
                  ))}
                </pre>
              </div>
            </Catch>
            <Catch title="Two buy buttons" text="The agent can't tell which one checks out.">
              <div className="relative flex gap-2.5" aria-hidden>
                <span className="absolute -top-[30px] left-1/2 -translate-x-1/2 font-mono text-[11.5px] whitespace-nowrap text-faint">2 matches for &quot;Buy&quot;</span>
                <span className="rounded-lg border border-[#3a3a3a] bg-[#0d0d0d] px-4 py-[9px] text-sm">Buy now</span>
                <span className="rounded-lg border border-[#3a3a3a] bg-[#0d0d0d] px-4 py-[9px] text-sm">Buy</span>
                <MousePointer2 className="absolute top-6 left-[118px] size-[22px] fill-foreground text-foreground" style={{ animation: "hesitate 3.4s var(--ease) infinite" }} />
              </div>
            </Catch>
            <Catch title="Paid, never marked paid" text="The money arrives. The order doesn't know.">
              <Rows rows={[["PayPal capture", "COMPLETED"], ["Store says", "Awaiting payment", true]]} />
            </Catch>
            <Catch title="Success after a cancel" text="The buyer cancels and the store says thank you.">
              <div className="relative w-60 rounded-[10px] border border-[#262626] bg-[#0b0b0b] p-4 text-center" aria-hidden>
                <b className="text-[15px]">Thanks for your order!</b>
                <small className="mt-2 block font-mono text-[11.5px] text-faint">PayPal order: VOIDED</small>
                <span className="absolute -top-3.5 -right-[18px] rotate-[8deg] rounded border-[1.5px] border-foreground bg-black px-2 py-1.5 font-mono text-[11px] leading-none font-semibold tracking-[0.12em]" style={{ animation: "stamp 3.2s var(--ease) infinite" }}>
                  CANCELLED
                </span>
              </div>
            </Catch>
            <Catch title="Duplicate order on retry" text="One slow click becomes two orders.">
              <Rows rows={[["#1042", "24.00 USD"], ["#1043", "24.00 USD", true]]} mono dup />
            </Catch>
          </div>
        </div>
      </section>

      <section data-cta className="relative overflow-hidden border-t py-24 text-center lg:py-[120px] lg:pb-[130px]">
        <div className={cn(wrap, "reveal-in relative")}>
          <h2 className="text-[clamp(32px,3.4vw,48px)] leading-[1.05] font-medium tracking-[-0.04em]">Find the bug before a shopper does.</h2>
          <p className="mt-3.5 text-base text-muted-foreground">Paste a link. On live stores the shopper browses but never pays.</p>
          <form onSubmit={paste} noValidate className="glass mx-auto mt-9 flex h-14 w-[min(560px,100%)] items-center gap-2.5 rounded-full py-0 pr-1.5 pl-5">
            <Globe className="size-[18px] flex-none text-faint" aria-hidden />
            <input
              type="url"
              inputMode="url"
              autoComplete="url"
              aria-label="Your store's web address"
              placeholder="https://your-store.com"
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              className="relative z-[1] min-w-0 flex-1 bg-transparent text-left text-[15px] outline-none placeholder:text-dim"
            />
            <button type="submit" disabled={busy} className={cn(white, "relative z-[1] disabled:opacity-60")}>
              Check my store <ArrowRight aria-hidden />
            </button>
          </form>
          {error && (
            <p role="alert" className="mt-3 text-sm text-bad">
              {error}
            </p>
          )}
          <button type="button" disabled={busy} onClick={() => start(null)} className="relative mt-[18px] inline-flex items-center gap-1.5 text-sm text-faint">
            <span>
              or <b className="font-medium text-foreground">run the demo store</b>, no keys needed
            </span>
            <ArrowRight className="size-3.5" aria-hidden />
          </button>
        </div>
      </section>

      <footer className="relative mt-2.5 bg-[#0a0a0a]">
        <div className="tear-top absolute inset-x-0 -top-2.5 h-2.5" aria-hidden />
        <div className={cn(wrap, "grid gap-10 pt-16 pb-[52px] sm:grid-cols-2 lg:grid-cols-[1.4fr_1fr_1fr_1fr]")}>
          <div>
            <div className="flex items-center gap-[9px] text-base font-semibold tracking-[-0.03em]">
              <Logo className="size-[22px]" />
              GhostShopper
            </div>
            <p className="mt-3 max-w-[300px] text-sm leading-[22px] text-muted-foreground">See your store through an AI shopper&apos;s eyes. Built during a hackathon. Not affiliated with PayPal.</p>
          </div>
          <FooterList title="Product" items={[["New check", "#/new"], ["My checks", "#/checks"], ["Sales ledger", "#/ledger"]]} />
          <FooterList title="Built with" items={[["PayPal Orders v2"], ["Kernel"], ["Channel3"], ["NVIDIA Nemotron"], ["AG Grid"]]} />
          <FooterList title="Project" items={[["Demo store", "/store/"], ["MIT license"]]} />
        </div>
        <div className="border-t-[1.5px] border-dashed border-[#2a2a2a]">
          <div className={cn(wrap, "flex flex-wrap justify-between gap-x-6 gap-y-2 pt-5 pb-7 font-mono text-xs tracking-[0.06em] text-faint")}>
            <span>1 STORE · 1 PRODUCT · 1 SCORE</span>
            <span>PAYMENTS RUN IN THE PAYPAL SANDBOX ONLY</span>
          </div>
        </div>
      </footer>
    </div>
  );
}

function Line({ op, label, hint, v, gone, dim }: { op: string; label: string; hint?: string; v: string; gone?: boolean; dim?: boolean }) {
  return (
    <div className={cn("grid grid-cols-[22px_1fr_auto] items-start gap-2.5 border-b border-dashed border-[#262626] py-[11px] transition-opacity duration-500", dim && "text-dim", gone && "line-through decoration-[#555] opacity-30")}>
      <span className="text-dim">{op}</span>
      <span>
        {label}
        {hint && <small className="mt-[3px] block font-sans text-[12.5px] text-[#8a8a8a]">{hint}</small>}
      </span>
      <span className="text-right">{v}</span>
    </div>
  );
}

function Catch({ wide, title, text, children }: { wide?: boolean; title: string; text: string; children: ReactNode }) {
  return (
    <div className={cn("glass lift reveal-in still-until-hover flex flex-col justify-end overflow-hidden p-6", wide && "sm:col-span-2")}>
      <div className="absolute inset-[18px_0_104px_0] grid place-items-center [&>*]:relative">
        <div className="absolute inset-0 [background:radial-gradient(circle,#2c2c2c_1px,transparent_1.3px)_0_0/18px_18px] [mask-image:radial-gradient(ellipse_60%_70%_at_50%_50%,#000_25%,transparent_75%)]" aria-hidden />
        {children}
      </div>
      <h3 className="relative text-[19px] font-medium tracking-[-0.04em]">{title}</h3>
      <p className="relative mt-[5px] max-w-[420px] text-sm leading-[21px] text-muted-foreground">{text}</p>
    </div>
  );
}

function Rows({ rows, mono, dup }: { rows: (readonly [string, string] | readonly [string, string, true])[]; mono?: boolean; dup?: boolean }) {
  return (
    <div className="w-[280px] max-w-full overflow-hidden rounded-[10px] border border-[#1f1f1f] bg-[#070707] text-[12.5px]" aria-hidden>
      {rows.map(([a, b, hit]) => (
        <div key={a} className={cn("flex justify-between border-b border-[#1a1a1a] px-[13px] py-2.5 last:border-b-0", hit && "shadow-[inset_0_0_0_1px_#6a6a6a] [background:radial-gradient(120%_160%_at_50%_0%,rgba(255,255,255,.12),rgba(255,255,255,.03))]")} style={hit && dup ? { animation: "dup 3.6s var(--ease) infinite" } : undefined}>
          <span className={mono ? "font-mono" : undefined}>{a}</span>
          <span className={cn(mono || a === "PayPal capture" ? "font-mono" : undefined)}>{b}</span>
        </div>
      ))}
    </div>
  );
}

function FooterList({ title, items }: { title: string; items: ([string] | [string, string])[] }) {
  return (
    <div>
      <h5 className="mb-3.5 text-sm leading-5 font-medium">{title}</h5>
      <ul className="grid gap-[9px] text-sm text-muted-foreground">
        {items.map(([label, href]) => (
          <li key={label}>
            {href ? (
              <a href={href} className="text-muted-foreground no-underline transition-colors hover:text-foreground">
                {label}
              </a>
            ) : (
              label
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}

