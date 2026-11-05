import { useEffect, useState } from "react";

// Day 1 placeholder: proves the frontend can reach the API. The dashboard (AG Grid) is built on Day 5.

type Health = { status: string; paypal_configured: boolean; paypal_env: string };

export default function App() {
  const [health, setHealth] = useState<Health | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetch("/api/health")
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`${r.status} ${r.statusText}`))))
      .then(setHealth)
      .catch((e: Error) => setError(e.message));
  }, []);

  return (
    <main style={{ fontFamily: "system-ui, sans-serif", padding: 24 }}>
      <h1>GhostShopper</h1>
      <p>See your store through an AI shopper's eyes.</p>
      {error && <p role="alert">API unreachable: {error}</p>}
      {health && (
        <p>
          API: {health.status} · PayPal ({health.paypal_env}):{" "}
          {health.paypal_configured ? "configured" : "not configured"}
        </p>
      )}
      <p>
        <a href="/store/">Open the demo store</a> · <a href="/store/admin">Flaw toggles</a>
      </p>
    </main>
  );
}
