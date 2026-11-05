// Types for the parts of the GhostShopper API the dashboard reads. Shapes follow backend/app/scorecard.py,
// recorder.load_run, agent/compare.py and market.py.

export type Health = {
  status: string;
  paypal_configured: boolean;
  paypal_mode: "mock" | "sandbox";
  groq_configured: boolean;
  demo_admin_open: boolean;
  retention_days: number;
};

export type FeedLine = { step: number; text: string; tone: "good" | "bad" | "info" | "neutral" };

export type PlainFix = {
  check: string;
  points: number;
  title: string;
  why: string;
  how: string;
  steps: string | null;
  platform: string | null;
  screenshot_url?: string | null;
};

export type Fix = {
  check: string;
  title: string;
  stage: string;
  severity: string;
  points: number;
  status: "failed" | "not_tested";
  code: string | null;
  reason: string | null;
  evidence: { url?: string; selector?: string; screenshot_url?: string };
  fix: string;
  fix_explained: string | null;
  plain: Omit<PlainFix, "check" | "points" | "screenshot_url"> | null;
};

export type NotFault = { check: string; title: string; points: number; reason: string | null; plain: string; kind: string };

export type Scorecard = {
  total: number;
  possible: number;
  rules_version: string;
  stages: Record<string, number>;
  stage_possible: Record<string, number>;
  fixes: Fix[];
  not_store_fault: NotFault[];
  not_checked_live: NotFault[];
  summary: string[];
  platform: string;
  simple: {
    score: number;
    label: string;
    of_what: string;
    status: "good" | "warn" | "bad" | "unknown";
    status_text: string;
    top_fixes: PlainFix[];
    more_fixes: number;
  };
};

export type Step = {
  idx: number;
  tool: string;
  args: Record<string, unknown> | null;
  thought: string | null;
  observation: string | null;
  ok: number;
  url: string | null;
  screenshot_path: string | null;
};

export type Order = {
  order_id: string;
  amount: string;
  currency: string;
  status: string;
  capture_id: string | null;
  capture_status: string | null;
  gross_amount: string | null;
  paypal_fee: string | null;
  net_amount: string | null;
};

export type Run = {
  id: number;
  status: "running" | "awaiting_human" | "completed" | "error";
  outcome: string | null;
  error: string | null;
  store_url: string;
  live: boolean;
  platform: string | null;
  llm: "mock" | "groq" | "scripted";
  model: string | null;
  paypal_mode: string;
  checkout: number;
  target_product: string;
  started_at: string;
  awaiting: { stage: string; reason: string; instructions: string; popup_url?: string } | null;
  feed: FeedLine[];
  steps: Step[];
  checks: { check_key: string; status: string; reason: string | null }[];
  order: Order | null;
  scorecard: Scorecard | null;
  mine: boolean; // started from this browser
  example: boolean; // a shared example check, readable by everyone
};

export type RunSummary = {
  id: number;
  started_at: string;
  status: string;
  outcome: string | null;
  live: number;
  store_url: string;
  score: number | null;
  score_possible: number | null;
  mine: boolean;
  example: boolean;
};

export type CompareItem = { check: string; title: string; points: number; fix: string | null; after_reason: string | null };

export type Compare = {
  before: { run_id: number; score: number; outcome: string };
  after: { run_id: number; score: number; outcome: string; order_id: string | null };
  score_change: number;
  fixed: CompareItem[];
  remaining: CompareItem[];
  new_failures: CompareItem[];
  warnings: string[];
};

export type Market = {
  source: "live" | "recorded";
  source_note?: string;
  our_price: string;
  currency: string;
  market_median: string | null;
  verdict: string;
  comparables: { title: string; price: string; domain: string }[];
};

export class ApiError extends Error {
  constructor(message: string, readonly status: number) {
    super(message);
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let resp: Response;
  try {
    resp = await fetch(path, { headers: { "Content-Type": "application/json" }, ...init });
  } catch {
    throw new ApiError("GhostShopper isn't responding.", 0);
  }
  const body = resp.status === 204 ? null : await resp.json().catch(() => null);
  if (!resp.ok) {
    const message = body?.detail?.message ?? (resp.status >= 500 ? "GhostShopper isn't responding." : resp.statusText);
    throw new ApiError(message, resp.status);
  }
  return body as T;
}

export const api = {
  health: () => request<Health>("/api/health"),
  runs: () => request<RunSummary[]>("/api/runs"),
  run: (id: number) => request<Run>(`/api/runs/${id}`),
  compareFor: (id: number) => request<Compare>(`/api/runs/${id}/compare`),
  deleteRun: (id: number) => request<null>(`/api/runs/${id}`, { method: "DELETE" }),
  devSummary: (id: number) => request<{ markdown: string }>(`/api/runs/${id}/developer-summary`),
  market: (sku: string) => request<Market>(`/api/market/${sku}`),
  start: (body: Record<string, unknown>) =>
    request<{ run_id: number }>("/api/runs", { method: "POST", body: JSON.stringify(body) }),
};

// The server picks the shopper (live AI when Groq is configured, otherwise the labelled scripted one) and,
// on the demo store, the PayPal purchase. A store link is the only thing a visitor chooses.
export function startCheck(storeUrl: string | null) {
  return api.start(storeUrl ? { store_url: storeUrl } : {});
}

// Two checks belong together when they are of the same store and from the same browser (or both examples).
export const sameSeries = (a: Pick<Run, "store_url" | "mine" | "example">, b: RunSummary) =>
  a.store_url === b.store_url && a.mine === b.mine && a.example === b.example;

export const DEMO_SKU = "FH-MUG-01";
