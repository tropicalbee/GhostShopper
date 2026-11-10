import { useEffect, useRef, useState } from "react";

// Hash routes, so a reload or a shared link lands on the same screen: #/, #/new, #/run/12, #/run/12/advanced.
// A query after the path (#/new?store=yours) is read with hashQuery.
export function useRoute(): string[] {
  const read = () => window.location.hash.replace(/^#\/?/, "").split("?")[0].split("/").filter(Boolean);
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

export const hashQuery = () => new URLSearchParams(window.location.hash.split("?")[1] ?? "");

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
  // The last payload as text, so a poll that brings nothing new does not re-render the screen.
  const last = useRef("");
  useEffect(() => {
    let alive = true;
    let timer: number | undefined;
    const run = () =>
      load()
        .then((d) => {
          if (!alive) return;
          const text = JSON.stringify(d);
          if (text !== last.current) {
            last.current = text;
            setData(d);
          }
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
