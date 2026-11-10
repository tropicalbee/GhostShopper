// Types for the parts of the GhostShopper API the dashboard reads. Shapes follow backend/app/scorecard.py,
// recorder.load_run, agent/compare.py and market.py.

export type Health = {
  status: string;
  paypal_configured: boolean;
  paypal_mode: "mock" | "sandbox";
  groq_configured: boolean;
  demo_admin_open: boolean;
  retention_days: number;
  real_checkout_available: boolean; // a run may pay with the real PayPal sandbox (needs keys and a Kernel browser)
  real_checkout_missing: string[]; // what the server still needs when it isn't
  real_payment_allowed: boolean; // this browser has the presenter unlock (or the server is a dev server)
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
  duration_ms: number | null;
  created_at: string;
};

export type TraceCell = { kind: "known" | "unknown" | "n/a" | "not_reached"; value: string | number | null; reason: string | null };

export type TraceStage = {
  key: "agent_wanted" | "store_order" | "paypal_order" | "paypal_capture" | "store_says";
  label: string;
  source: string | null; // step, order number or PayPal id
  cells: Record<"product" | "quantity" | "amount" | "currency" | "status", TraceCell>;
  evidence: { step?: number; screenshot?: string };
};

// One id that should match across two records of the same purchase. Evidence only.
export type TraceLink = {
  key: "store_to_paypal_order" | "paypal_order_to_store" | "capture_to_paypal_order" | "store_to_capture";
  label: string;
  expected: string | null;
  actual: string | null;
  kind: "ok" | "broken" | "unknown" | "n/a";
  reason: string | null;
};

export type TraceMismatch = {
  stage: TraceStage["key"];
  field: keyof TraceStage["cells"] | TraceLink["key"]; // a link key when an id link is broken
  expected: string | number | null;
  actual: string | number | null;
  explanation: string;
  fix: string;
  first: boolean;
};

// Shape follows backend/app/trace.py (build_trace). Evidence only: it never changes the score.
export type Trace = {
  stages: TraceStage[];
  mismatches: TraceMismatch[];
  links?: TraceLink[];
  first_mismatch: TraceMismatch | null;
  counts: { mismatch: number; unknown: number };
};

// Shape follows backend/app/agent/injection.py and loop.py (SafetyLog). The shopper never follows them.
export type SafetyFinding = { where: string; excerpt: string; hidden: boolean; step: number | null; screenshot: string | null };
export type AgentSafety = { findings: SafetyFinding[]; followed: boolean };

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
  refund_id: string | null;
  refund_status: string | null;
  refund_amount: string | null;
  refund_currency: string | null;
  created_at: string;
  captured_at: string | null;
  refunded_at: string | null;
};

export type Refund = {
  order_id: string;
  refund_id: string;
  status: string;
  amount: string;
  currency: string;
  verified: boolean;
  mismatches: string[];
  refunded_at?: string | null;
};

export type PayPalItem = {
  key: string;
  label: string;
  status: "detected" | "partial" | "not_confirmed" | "missing";
  points: number;
  max: number;
  evidence: string[];
  note: string;
};

export type PayPalRecommendation = { key: string; title: string; why: string; docs_url: string; points: number };

// Shape follows backend/app/agent/paypal_readiness.py (build_readiness).
export type PayPalReadiness = {
  version: string;
  score: number;
  paypal_found: boolean;
  status: "good" | "warn" | "bad";
  sdk: { version: "v5" | "v6"; src: string | null; mock: boolean; components: string[]; currency: string | null; intent: string | null } | null;
  steps_to_paypal: number | null;
  placement: { product: boolean; cart: boolean; checkout: boolean };
  pages_scanned: { url: string; kind: string; button: boolean }[];
  checklist: PayPalItem[];
  recommendations: PayPalRecommendation[];
};

export type FeedField = {
  field: string;
  required: boolean;
  status: "found" | "partial" | "missing";
  value: string | null;
  source: string | null;
  note: string | null;
  fix: string | null;
};

// Shape follows backend/app/feed.py (build_feed). null when the shopper never read a product page.
export type ProductFeed = {
  row: Record<string, string>;
  fields: FeedField[];
  required_found: number;
  required_total: number;
  ready: boolean;
  source_url: string | null;
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
  budget: string | null; // the shopper's spending limit in USD, like "30.00"
  target_product: string;
  started_at: string;
  finished_at: string | null;
  awaiting: { stage: string; reason: string; instructions: string; popup_url?: string; live_view_url?: string | null } | null;
  feed: FeedLine[];
  steps: Step[];
  checks: { check_key: string; stage: string; status: string; cause: string | null; reason: string | null; code?: string | null; evidence?: Record<string, unknown> | null }[];
  order: Order | null;
  catalog_price: { amount: string; currency: string } | null; // the demo store's own price for the target product; null on live stores
  scorecard: Scorecard | null;
  paypal_readiness: PayPalReadiness | null; // null on checks made before this existed
  product_feed: ProductFeed | null; // null when no product page was read, and on checks made before this existed
  trace: Trace;
  agent_safety: AgentSafety;
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

export type Rubric = { rules_version: string; stages: { key: string; points: number; checks: number }[] };

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
  // Newest first. Fewer than `limit` rows back means the end; `before` pages from a run id.
  runs: (params: { limit?: number; before?: number } = {}) => {
    const q = new URLSearchParams();
    if (params.limit) q.set("limit", String(params.limit));
    if (params.before) q.set("before", String(params.before));
    return request<RunSummary[]>(`/api/runs${q.size ? `?${q}` : ""}`);
  },
  run: (id: number) => request<Run>(`/api/runs/${id}`),
  compareFor: (id: number) => request<Compare>(`/api/runs/${id}/compare`),
  deleteRun: (id: number) => request<null>(`/api/runs/${id}`, { method: "DELETE" }),
  devSummary: (id: number) => request<{ markdown: string }>(`/api/runs/${id}/developer-summary`),
  market: (sku: string) => request<Market>(`/api/market/${sku}`),
  refund: (orderId: string) => request<Refund>(`/api/paypal/orders/${orderId}/refund`, { method: "POST" }),
  rubric: () => request<Rubric>("/api/rubric"),
  start: (body: Record<string, unknown>) =>
    request<{ run_id: number }>("/api/runs", { method: "POST", body: JSON.stringify(body) }),
};

// The server picks the shopper (live AI when Groq is configured, otherwise the labelled scripted one) and,
// on the demo store, the PayPal purchase. A visitor chooses a store link and, optionally, a spending limit.
// A spending limit only matters where the shopper pays, which is the demo store.
// realPayment asks for the real PayPal sandbox on the demo store; without it the server's default applies.
export function startCheck(storeUrl: string | null, budget?: string | null, realPayment?: boolean) {
  return api.start({
    ...(storeUrl ? { store_url: storeUrl } : {}),
    ...(budget ? { budget } : {}),
    ...(realPayment ? { real_payment: true } : {}),
  });
}

// Two checks belong together when they are of the same store and from the same browser (or both examples).
export const sameSeries = (a: Pick<Run, "store_url" | "mine" | "example">, b: RunSummary) =>
  a.store_url === b.store_url && a.mine === b.mine && a.example === b.example;

// How many recent checks the sidebar and the history chart need.
export const RECENT_RUNS = 50;

export const DEMO_SKU = "FH-MUG-01";
// The demo store's one product (store/catalog.py), the same in every demo check.
export const DEMO_PRODUCT = { name: "Speckled Stoneware Mug", price: "24.00 USD" };

// The file name of a step's screenshot, as GET /api/runs/{id}/files/{name} takes it.
export const shotName = (path: string | null) => (path ? path.split(/[\/]/).pop() ?? null : null);
export const shotUrl = (runId: number, name: string) => `/api/runs/${runId}/files/${name}`;

// What the store's problems are called. The API gives keys and on/off only (GET /store/admin/flaws.json).
export type FlawState = Record<string, boolean>;
export const storeApi = {
  flaws: () => request<FlawState>("/store/admin/flaws.json"),
  setFlaws: (flaws: FlawState) => request<FlawState>("/store/admin/flaws.json", { method: "PUT", body: JSON.stringify({ flaws }) }),
};
