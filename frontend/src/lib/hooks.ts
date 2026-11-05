import { useEffect, useState } from "react";

// Hash routes, so a reload or a shared link lands on the same screen: #/, #/run/12, #/run/12/advanced, #/compare.
export function useRoute(): string[] {
  const read = () => window.location.hash.replace(/^#\/?/, "").split("/").filter(Boolean);
  const [parts, setParts] = useState(read);
  useEffect(() => {
    const onChange = () => {
      setParts(read());
      window.scrollTo(0, 0);
    };
    window.addEventListener("hashchange", onChange);
    return () => window.removeEventListener("hashchange", onChange);
  }, []);
  return parts;
}

export const go = (path: string) => {
  window.location.hash = path;
};

export function useMediaQuery(query: string): boolean {
  const [matches, setMatches] = useState(() => window.matchMedia(query).matches);
  useEffect(() => {
    const mql = window.matchMedia(query);
    const onChange = () => setMatches(mql.matches);
    mql.addEventListener("change", onChange);
    return () => mql.removeEventListener("change", onChange);
  }, [query]);
  return matches;
}

// Counts from `from` to `to` once. Jumps straight to `to` under prefers-reduced-motion.
export function useCountUp(to: number, from = 0, ms = 1200): number {
  const reduced = useMediaQuery("(prefers-reduced-motion: reduce)");
  const [value, setValue] = useState(reduced ? to : from);
  useEffect(() => {
    if (reduced) {
      setValue(to);
      return;
    }
    let frame = 0;
    const start = performance.now();
    const tick = (now: number) => {
      const t = Math.min(1, (now - start) / ms);
      setValue(Math.round(from + (to - from) * (1 - (1 - t) ** 3)));
      if (t < 1) frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [to, from, ms, reduced]);
  return value;
}

// Fetches once, or every `pollMs` while `keepPolling` says so.
export function useFetch<T>(load: () => Promise<T>, deps: unknown[], pollMs?: number, keepPolling?: (data: T) => boolean) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [status, setStatus] = useState<number | null>(null); // HTTP status of the last error, 0 = no answer
  const [nonce, setNonce] = useState(0);
  useEffect(() => {
    let alive = true;
    let timer: number | undefined;
    const run = () =>
      load()
        .then((d) => {
          if (!alive) return;
          setData(d);
          setError(null);
          setStatus(null);
          if (pollMs && keepPolling?.(d)) timer = window.setTimeout(run, pollMs);
        })
        .catch((e: Error & { status?: number }) => {
          if (!alive) return;
          setError(e.message);
          setStatus(e.status ?? 0);
        });
    run();
    return () => {
      alive = false;
      window.clearTimeout(timer);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, nonce]);
  return { data, error, status, retry: () => setNonce((n) => n + 1) };
}
