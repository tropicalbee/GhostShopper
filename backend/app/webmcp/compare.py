"""Browser agent vs WebMCP tools on the same store: what each path cost and where each purchase ended.

    python -m backend.app.webmcp compare <browser_run> <webmcp_run>
    python -m backend.app.webmcp compare --last

compare_paths is a pure function over two run payloads that each carry their purchase trace (run["trace"]); the verdict
is computed here, never by an LLM.
"""

from datetime import datetime
from pathlib import Path
from typing import Any

from store import catalog

from .. import db
from ..trace import BUYER_APPROVAL_TOOL, KNOWN, OK, READ_BACK_TOOL
from .tools import INITIATE

RUNTIME_TOOLS = (READ_BACK_TOOL, BUYER_APPROVAL_TOOL)  # steps the runtime took, not the agent
ACTORS = {"browser": "The browser agent", "webmcp": "WebMCP"}


class PathCompareError(LookupError):
    pass


def _seconds(run: dict[str, Any]) -> float | None:
    if not run.get("finished_at"):
        return None
    return round((datetime.fromisoformat(run["finished_at"]) - datetime.fromisoformat(run["started_at"])).total_seconds(), 1)


def _handoff(run: dict[str, Any]) -> str:
    tools = {s["tool"] for s in run["steps"]}
    if run["path"] == "webmcp":
        host = ((run.get("webmcp") or {}).get("handoff") or {}).get("approval_url_host")
        return f"WebMCP approval_url{f' ({host})' if host else ''}" if INITIATE in tools else "none"
    if "pay_with_saved_paypal" in tools:
        return "vault (saved PayPal account)"
    return "browser popup (PayPal button)" if "pay_with_paypal" in tools else "none"


def _bought(run: dict[str, Any]) -> str | None:
    sku = (run.get("order") or {}).get("sku")
    if sku is None:
        sku = next(((s.get("args") or {}).get("product_id") for s in run["steps"] if s["tool"] == INITIATE), None)
    product = catalog.get_by_sku(sku) if sku else None
    return product.name if product else sku


def _captured(run: dict[str, Any]) -> str | None:
    order = run.get("order")
    if order:
        return order.get("gross_amount") or order.get("amount")
    amount = ((run.get("webmcp") or {}).get("completion") or {}).get("amount")
    return amount.get("value") if isinstance(amount, dict) else None


def _status_of(trace: dict[str, Any], stage: str) -> str | None:
    cell = next(s for s in trace["stages"] if s["key"] == stage)["cells"]["status"]
    return cell["value"] if cell["kind"] == KNOWN else None


def _side(run: dict[str, Any]) -> dict[str, Any]:
    trace = run["trace"]
    agent_steps = [s for s in run["steps"] if s["tool"] not in RUNTIME_TOOLS and s["tool"] != "finish"]
    calls: dict[str, int] = {}
    for step in agent_steps:
        calls[step["tool"]] = calls.get(step["tool"], 0) + 1
    first = trace["first_mismatch"]
    return {
        "run_id": run["id"], "path": run["path"], "outcome": run["outcome"], "external_demo": bool((run.get("webmcp") or {}).get("external_demo")),
        "steps": run["step_count"], "agent_steps": len(agent_steps),
        "llm_turns": (run.get("webmcp") or {}).get("llm_turns"),  # the browser path does not record its turns
        "tool_calls": calls, "duration_s": _seconds(run),
        "product": {"target": run["target_product"], "bought": _bought(run)},
        "price": {"catalog": (run.get("catalog_price") or {}).get("amount"), "captured": _captured(run)},
        "handoff": _handoff(run),
        "final": {
            "trace_overall": "mismatch" if first else "no mismatch found",
            "first_mismatch": ({k: first[k] for k in ("stage", "field", "expected", "actual", "explanation")} if first else None),
            "store_order_status": _status_of(trace, "store_order"),
            "store_says": _status_of(trace, "store_says"),
            "links_ok": sum(link["kind"] == OK for link in trace["links"]), "links_total": len(trace["links"]),
        },
        "tool_checks": (run.get("webmcp") or {}).get("tool_checks"),  # a checklist of the tools, not a score
        "score": run["score"]["total"] if run.get("score") else None,  # the readiness score rates the page path only
    }


PLACES = {"agent_wanted": "what the agent wanted", "store_order": "store order", "paypal_order": "PayPal order",
          "paypal_capture": "PayPal capture", "store_says": "order page"}


def _describe(first: dict[str, Any]) -> str:
    place = PLACES.get(first["stage"], first["stage"].replace("_", " "))
    if first["field"] == "status":
        return f"the {place} still says {first['actual']}"
    return f"the {place} {first['field']} was {first['actual']}"


def _verdict(browser: dict[str, Any], webmcp: dict[str, Any]) -> str:
    def took(side: dict[str, Any]) -> str:
        unit = "tool calls" if side["path"] == "webmcp" else "steps"
        return f"{side['agent_steps']} {unit}"

    bought = [side["outcome"] == "purchased" for side in (webmcp, browser)]
    if all(bought):
        head = f"WebMCP bought in {took(webmcp)}; the browser agent took {took(browser)}."
    else:
        def part(side: dict[str, Any]) -> str:
            return f"bought in {took(side)}" if side["outcome"] == "purchased" else f"did not buy (outcome: {side['outcome']})"
        head = f"WebMCP {part(webmcp)}; the browser agent {part(browser)}."
    if not all(bought):
        return head
    a, b = browser["final"]["first_mismatch"], webmcp["final"]["first_mismatch"]
    if a and b and (a["stage"], a["field"], a["actual"]) == (b["stage"], b["field"], b["actual"]):
        return f"{head} Both paths hit the same first mismatch: {_describe(a)}."
    if a and b:
        return f"{head} They hit different first mismatches: the browser path at {_describe(a)}, WebMCP at {_describe(b)}."
    if a or b:
        return f"{head} Only the {'browser' if a else 'WebMCP'} path hit a mismatch: {_describe(a or b)}."
    return f"{head} Both purchases reconcile at every stage."


def compare_paths(first: dict[str, Any], second: dict[str, Any]) -> dict[str, Any]:
    """Two finished runs of the same store, one per path, in either order. Each run needs its "trace"."""
    if {first["path"], second["path"]} != {"browser", "webmcp"}:
        raise PathCompareError("Compare one browser check with one WebMCP check.")
    if first["store_url"] != second["store_url"]:
        raise PathCompareError("Both checks need to be of the same store.")
    browser, webmcp = (first, second) if first["path"] == "browser" else (second, first)
    sides = {"browser": _side(browser), "webmcp": _side(webmcp)}
    warnings = []
    if browser["target_product"] != webmcp["target_product"]:
        warnings.append("The two checks shopped for different products.")
    if browser["flaws_snapshot"] != webmcp["flaws_snapshot"]:
        warnings.append("The store's flaw settings were different in the two checks.")
    return {**sides, "verdict": _verdict(sides["browser"], sides["webmcp"]), "warnings": warnings}


def latest_of_path(db_path: Path, like_run: dict[str, Any], path: str) -> int | None:
    """The latest finished check of this path on the same store by the same browser as like_run."""
    with db.connect(db_path) as conn:
        row = conn.execute(
            "SELECT id FROM runs WHERE store_url = ? AND owner_hash IS ? AND path = ? AND status = 'completed' AND id != ?"
            " ORDER BY id DESC LIMIT 1", (like_run["store_url"], like_run["owner_hash"], path, like_run["id"])).fetchone()
    return row[0] if row else None


def latest_pair(db_path: Path) -> tuple[int, int]:
    """(browser run, webmcp run): the latest WebMCP run and the latest browser run on the same store."""
    with db.connect(db_path) as conn:
        webmcp = conn.execute("SELECT id, store_url, owner_hash FROM runs WHERE path = 'webmcp' AND status = 'completed'"
                              " ORDER BY id DESC LIMIT 1").fetchone()
        browser = webmcp and conn.execute(
            "SELECT id FROM runs WHERE path = 'browser' AND status = 'completed' AND store_url = ? AND owner_hash IS ?"
            " ORDER BY id DESC LIMIT 1", (webmcp["store_url"], webmcp["owner_hash"])).fetchone()
    if not webmcp or not browser:
        raise PathCompareError("Need a finished browser check and a finished WebMCP check of the same store.")
    return browser["id"], webmcp["id"]
