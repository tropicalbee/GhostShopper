export { cn } from "cn"

export const REPO_URL = "https://github.com/tropicalbee/GhostShopper";

// Checks recorded on a local server mention its address in their text; show the store's own path instead.
const LOCAL_ORIGIN = /https?:\/\/(?:localhost|127\.0\.0\.1)(?::\d+)?(?=\/)/g;
export function stripLocalOrigin<T>(text: T): T {
  return (typeof text === "string" ? text.replace(LOCAL_ORIGIN, "") : text) as T;
}
