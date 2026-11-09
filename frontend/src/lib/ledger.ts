import { ApiError } from "@/lib/api";

export type LedgerOutcome = "captured" | "refunded" | "lost" | "at_risk";
export type PayPalReported = "matched" | "pending" | "mismatch" | "not_checked";

export type LedgerRow = {
  time: string | null;
  source: "agent" | "human";
  run_id: number | null;
  store_state: string[] | null; // flaws that were on; null = unknown
  outcome: LedgerOutcome;
  stopped_at: string | null;
  amount_at_stake: string | null;
  order_id: string | null;
  capture_id: string | null;
  gross: string | null;
  fee: string | null;
  net: string | null;
  refund: string | null;
  currency: string | null;
  paypal_mode: string;
  paypal_reported: PayPalReported;
  paypal_status: string | null;
};

export type LedgerTotals = { lost: string; captured_gross: string; fees: string; net: string; refunded: string; currency: string };

export type Ledger = {
  rows: LedgerRow[];
  totals: LedgerTotals;
  paypal_error: string | null;
  paypal_window: { start: string; end: string } | null;
};

export async function fetchLedger(): Promise<Ledger> {
  let resp: Response;
  try {
    resp = await fetch("/api/ledger");
  } catch {
    throw new ApiError("GhostShopper isn't responding.", 0);
  }
  const body = await resp.json().catch(() => null);
  if (!resp.ok) throw new ApiError(body?.detail?.message ?? resp.statusText, resp.status);
  return body as Ledger;
}

export const OUTCOME_LABEL: Record<LedgerOutcome, string> = {
  captured: "Captured",
  refunded: "Refunded",
  lost: "Lost sale",
  at_risk: "At risk",
};

export const REPORTED_LABEL: Record<PayPalReported, string> = {
  matched: "Matched",
  pending: "Pending",
  mismatch: "Mismatch",
  not_checked: "Not checked",
};

// PayPal's transaction status codes, spelled out.
export const PAYPAL_STATUS: Record<string, string> = { S: "Completed", P: "Pending", D: "Denied", V: "Reversed" };

export type LedgerPreset = "all" | "lost" | "agent" | "unmatched";

export function matchesPreset(row: LedgerRow, preset: LedgerPreset): boolean {
  if (preset === "lost") return row.outcome === "lost";
  if (preset === "agent") return row.source === "agent";
  if (preset === "unmatched") return row.capture_id !== null && row.paypal_reported !== "matched";
  return true;
}
