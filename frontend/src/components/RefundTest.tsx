import { useState } from "react";

import { Button } from "@/components/ui/button";
import { api, type Refund, type Run } from "@/lib/api";

// What the stored order says about its refund, in the shape the refund call answers with.
export function refundedOf(o: NonNullable<Run["order"]>): Refund | null {
  if (!o.refund_id || !o.refund_status || !o.refund_amount) return null;
  const mismatches = [];
  if (o.refund_status !== "COMPLETED") mismatches.push(`Refund status is ${o.refund_status}`);
  if (o.refund_amount !== (o.gross_amount ?? o.amount)) mismatches.push(`Refunded ${o.refund_amount}, but ${o.gross_amount ?? o.amount} was captured`);
  return { order_id: o.order_id, refund_id: o.refund_id, status: o.refund_status, amount: o.refund_amount, currency: o.refund_currency ?? o.currency, verified: !mismatches.length, mismatches, refunded_at: o.refunded_at };
}

// Gives the test payment back and shows what PayPal reports. The refund is not part of the score.
// showResult=false leaves the outcome to the caller, which gets it through onRefunded.
export function RefundTest({
  orderId,
  currency,
  refunded,
  onRefunded,
  showResult = true,
}: {
  orderId: string;
  currency: string;
  refunded: Refund | null;
  onRefunded?: (r: Refund) => void;
  showResult?: boolean;
}) {
  const [result, setResult] = useState<Refund | null>(refunded);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const refund = async () => {
    setBusy(true);
    setError(null);
    try {
      const done = await api.refund(orderId);
      setResult(done);
      onRefunded?.(done);
    } catch (e) {
      setError((e as Error).message);
    }
    setBusy(false);
  };
  if (result) {
    if (!showResult) return null;
    return (
      <div className="mt-4 text-sm" role="status">
        <p>Refund {result.status.toLowerCase()}: <span className="num">{result.amount} {result.currency || currency}</span></p>
        {result.verified ? (
          <p className="mt-1 font-medium text-good">Money returned: verified</p>
        ) : (
          <ul className="mt-1 text-bad">{result.mismatches.map((m) => <li key={m}>{m}</li>)}</ul>
        )}
      </div>
    );
  }
  return (
    <div className="mt-4">
      <Button variant="outline" onClick={refund} disabled={busy} className="h-10">
        {busy ? "Refunding…" : "Refund test payment"}
      </Button>
      {error && <p role="alert" className="mt-2 text-sm text-bad">{error}</p>}
    </div>
  );
}
