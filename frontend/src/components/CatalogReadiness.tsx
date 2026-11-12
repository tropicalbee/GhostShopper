import { useFetch } from "@/lib/hooks";
import type { Run } from "@/lib/api";

type CatalogProduct = { url: string; name: string; missing: string[]; machine_readable: boolean };
type Catalog = {
  store_url: string;
  products_checked: number;
  machine_readable: number;
  percent: number | null; // null when too few pages could be checked for a figure
  benchmark_percent: number;
  meets_benchmark: boolean | null;
  summary: string;
  per_product: CatalogProduct[];
  source: "demo store" | "live store";
  errors: string[];
};

async function fetchCatalog(storeUrl: string | null): Promise<Catalog> {
  const resp = await fetch(`/api/catalog${storeUrl ? `?store_url=${encodeURIComponent(storeUrl)}` : ""}`).catch(() => null);
  if (!resp) throw new Error("GhostShopper isn't responding.");
  const body = await resp.json().catch(() => null);
  if (!resp.ok) throw new Error(body?.detail?.message ?? (resp.status >= 500 ? "GhostShopper isn't responding." : resp.statusText));
  return body as Catalog;
}

const NOTE =
  "PayPal's Agentic Commerce Pulse Report found only about 1 in 5 merchants have 80% or more of their catalog as structured data AI agents can read. A product counts when its JSON-LD has the Product type, name, price, currency and availability. This is not part of the score.";

// Advanced view: the share of up to 12 product pages whose structured data an AI agent can read.
export function CatalogReadiness({ run }: { run: Run }) {
  const storeUrl = run.live ? run.store_url : null;
  const { data, error } = useFetch(() => fetchCatalog(storeUrl), [storeUrl]);
  if (error) return <p className="border-t-[1.5px] border-rule py-8 text-foreground">{error}</p>;
  if (!data) return <div className="hatch h-64 border-y-[1.5px] border-t-rule" role="status" aria-busy="true" aria-label="Checking the catalog" />;
  return (
    <div className="border-t-[1.5px] border-rule pt-5">
      <p className="font-medium">{data.summary}</p>
      <p className="mt-1 max-w-2xl text-sm text-muted-foreground">{NOTE}</p>
      {data.percent !== null && (
        <>
      <div
        className="relative mt-6 h-3 border"
        role="img"
        aria-label={`${data.percent}% of products are machine-readable. The benchmark is ${data.benchmark_percent}%.`}
      >
        <div className="h-full bg-earned" style={{ width: `${data.percent}%` }} />
        <span className="absolute -top-2 -bottom-2 w-0.5 bg-foreground" style={{ left: `${data.benchmark_percent}%` }} aria-hidden />
      </div>
      <div className="num relative mt-2 h-4 text-xs text-muted-foreground">
        <span className="absolute left-0">{data.percent}% of products</span>
        <span className="absolute -translate-x-1/2" style={{ left: `${data.benchmark_percent}%` }}>{data.benchmark_percent}% benchmark</span>
      </div>
        </>
      )}
      <div className="mt-6 overflow-x-auto">
        <table className="w-full text-left text-sm">
          <thead>
            <tr className="border-b-[1.5px] border-rule text-muted-foreground">
              <th scope="col" className="py-2.5 pr-4 font-normal">Product</th>
              <th scope="col" className="py-2.5 pr-4 font-normal">Machine-readable</th>
              <th scope="col" className="py-2.5 font-normal">Missing</th>
            </tr>
          </thead>
          <tbody>
            {data.per_product.map((p) => (
              <tr key={p.url} className="border-b align-top">
                <td className="py-2.5 pr-4 [overflow-wrap:anywhere]">
                  <a href={p.url} target="_blank" rel="noreferrer" className="underline-offset-4 hover:underline">{p.name}</a>
                </td>
                <td className="py-2.5 pr-4">{p.machine_readable ? "Yes" : "No"}</td>
                <td className="num py-2.5 text-muted-foreground">{p.missing.length ? p.missing.join(", ") : "Nothing"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {data.errors.length > 0 && (
        <ul className="mt-3 text-[13px] text-muted-foreground">
          {data.errors.map((e) => <li key={e} className="[overflow-wrap:anywhere]">Could not check: {e}</li>)}
        </ul>
      )}
      <p className="mt-3 text-[13px] text-muted-foreground">
        {data.source === "demo store" ? "Read from the demo store as it is now, so it follows the flaw toggles, not the moment of the check." : `Read from ${data.store_url}.`}
      </p>
    </div>
  );
}
