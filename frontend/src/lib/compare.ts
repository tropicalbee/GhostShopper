// Types and row building for the before/after grid (GET /api/runs/{id}/compare). Everything shown here comes
// from the deterministic comparison; nothing is computed by the model.

export type CheckStatus = "pass" | "fail" | "not_tested";

export type CompareOrder = {
  amount: string;
  currency: string;
  capture_status: string | null;
  gross_amount: string | null;
  net_amount: string | null;
};

export type CompareSide = {
  run_id: number;
  score: number;
  possible: number;
  outcome: string;
  order: CompareOrder | null;
  catalog_price: { amount: string; currency: string } | null;
};

export type CompareCheck = {
  check: string;
  title: string;
  stage: string;
  points: number;
  before: string;
  after: string;
  fix_applied: string | null;
};

export type CompareData = {
  before: CompareSide;
  after: CompareSide;
  score_change: number;
  warnings: string[];
  checks: CompareCheck[];
};

export type GridRow = {
  kind: "check" | "total" | "money";
  check: string;
  stage: string;
  points: number | null;
  before: string;
  after: string;
  gained: number | null;
  fix: string;
};

export const STAGE_ORDER = ["discover", "details", "checkout", "payment", "outcome"];
export const STAGE_LABEL: Record<string, string> = { discover: "Find", details: "Details", checkout: "Checkout", payment: "Payment", outcome: "Finish" };

export const STATUS_LABEL: Record<CheckStatus, string> = { pass: "Pass", fail: "Fail", not_tested: "Not tested" };

export const asStatus = (s: string): CheckStatus => (s === "pass" ? "pass" : s === "fail" ? "fail" : "not_tested");

export function money(value: string | number, currency: string): string | null {
  try {
    return new Intl.NumberFormat("en-US", { style: "currency", currency }).format(Number(value));
  } catch {
    return null; // not a currency code Intl knows: show nothing rather than guess
  }
}

// "Lost $24.00" when the shopper left without paying, "Captured $24.00, net $23.06" when the sale went through.
// A figure that isn't in the run's data is left out.
export function moneyText(s: CompareSide): string {
  const o = s.order?.capture_status === "COMPLETED" ? s.order : null;
  if (o) {
    const gross = money(o.gross_amount ?? o.amount, o.currency);
    const net = o.net_amount ? money(o.net_amount, o.currency) : null;
    return [gross && `Captured ${gross}`, net && `net ${net}`].filter(Boolean).join(", ") || "Captured";
  }
  const price = s.catalog_price ? money(s.catalog_price.amount, s.catalog_price.currency) : null;
  return price ? `Lost ${price}` : "No sale";
}

export function gainedPoints(c: Pick<CompareCheck, "before" | "after" | "points">): number {
  const b = asStatus(c.before);
  const a = asStatus(c.after);
  if (b !== "pass" && a === "pass") return c.points;
  if (b === "pass" && a !== "pass") return -c.points;
  return 0;
}

export function checkRows(data: CompareData): GridRow[] {
  return data.checks.map((c) => ({
    kind: "check",
    check: c.title,
    stage: c.stage,
    points: c.points,
    before: asStatus(c.before),
    after: asStatus(c.after),
    gained: gainedPoints(c),
    fix: asStatus(c.before) === "fail" ? (c.fix_applied ?? "") : "",
  }));
}

export function pinnedRows(data: CompareData): GridRow[] {
  const blank = { stage: "", points: null, fix: "" };
  return [
    {
      ...blank,
      kind: "total",
      check: "Total score",
      points: data.after.possible,
      before: String(data.before.score),
      after: String(data.after.score),
      gained: data.score_change,
    },
    { ...blank, kind: "money", check: "Money", before: moneyText(data.before), after: moneyText(data.after), gained: null },
  ];
}

export async function fetchCompare(afterId: number, beforeId?: number): Promise<CompareData | null> {
  const q = beforeId ? `?before=${beforeId}` : "";
  const resp = await fetch(`/api/runs/${afterId}/compare${q}`);
  if (resp.status === 404) return null; // nothing earlier to compare with
  if (!resp.ok) throw new Error("We couldn't load the before and after.");
  return (await resp.json()) as CompareData;
}
