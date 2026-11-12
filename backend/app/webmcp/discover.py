"""Find the tools a page registers with WebMCP and call them.

Primary path: the browser's native WebMCP, through the Chrome DevTools Protocol WebMCP domain (WebMCP.toolsAdded to
discover, WebMCP.invokeTool / WebMCP.toolResponded to call), the way a browser-integrated agent sees a page's tools.
It needs Chromium launched with LAUNCH_ARGS. Fallback: shim.js records what the page registers, for browsers with no
native WebMCP (for example a Kernel browser without the flag). The report says which one was used.
"""

import asyncio
import json
import time
from pathlib import Path
from typing import Any

from playwright.async_api import Error as PlaywrightError
from playwright.async_api import Page

SHIM_PATH = Path(__file__).with_name("shim.js")
LAUNCH_ARGS = ["--enable-features=WebMCP"]
NATIVE_SOURCE = "native WebMCP (Chromium, CDP WebMCP domain)"
SHIM_SOURCE = "GhostShopper test shim (browser has no native WebMCP)"
SETTLE_S = 0.6  # the tool list must stop growing for this long: a page registers its tools one after another

STATE_JS = """() => {
  const s = window.__ghostWebMCP;
  if (!s) return null;
  const plain = v => (v === undefined ? null : JSON.parse(JSON.stringify(v)));
  return {
    native: s.native,
    context: plain(s.context),
    tools: Object.values(s.tools).map(t => ({
      name: t.name, description: t.description || '', input_schema: plain(t.inputSchema) || {},
      read_only: !!(t.annotations && t.annotations.readOnlyHint)})),
    scripts: [...document.scripts].map(x => x.src).filter(Boolean),
  };
}"""

CALL_JS = """async ([name, args]) => {
  const tool = window.__ghostWebMCP && window.__ghostWebMCP.tools[name];
  if (!tool) return {missing: true};
  try {
    const result = await tool.execute(args);
    return {ok: true, result: result === undefined ? null : JSON.parse(JSON.stringify(result))};
  } catch (err) {
    return {ok: false, error: String((err && err.message) || err)};
  }
}"""


class WebMCPToolError(Exception):
    """The tool is not on the page, or it threw."""


async def install_shim(context: Any) -> None:
    await context.add_init_script(path=SHIM_PATH)


def unwrap(result: dict[str, Any] | None) -> dict[str, Any]:
    """A tool's structuredContent, or its text content parsed as JSON."""
    result = result or {}
    if isinstance(result.get("structuredContent"), dict):
        return result["structuredContent"]
    for part in result.get("content") or []:
        if part.get("type") == "text":
            try:
                parsed = json.loads(part["text"])
            except (TypeError, ValueError):
                return {"text": part.get("text")}
            return parsed if isinstance(parsed, dict) else {"value": parsed}
    return {}


async def _shim_state(page: Page) -> dict[str, Any] | None:
    return await page.evaluate(STATE_JS)


def _report(page: Page, source: str | None, tools: list[dict[str, Any]], state: dict[str, Any] | None) -> dict[str, Any]:
    scripts = (state or {}).get("scripts", [])
    return {
        "url": page.url, "source": source, "tools": sorted(tools, key=lambda t: t["name"]),
        "context": (state or {}).get("context"),
        "paypal_sdk_v6": any("/web-sdk/v6/core" in s for s in scripts),
        "webmcp_script": any("webmcp" in s.lower() for s in scripts),
        "scripts": scripts,
    }


async def discover(page: Page, timeout_s: float = 10.0) -> dict[str, Any]:
    """The shim's view of the page (see Tools.discover for the native one). Registration is async and retried by the
    page, so wait for it."""
    deadline = time.monotonic() + timeout_s
    state: dict[str, Any] | None = None
    stable_since, count = time.monotonic(), -1
    while time.monotonic() < deadline:
        state = await _shim_state(page)
        now = time.monotonic()
        found = len(state["tools"]) if state else 0
        if found != count:
            count, stable_since = found, now
        elif found and now - stable_since >= SETTLE_S:
            break
        await page.wait_for_timeout(150)
    source = None if state is None else NATIVE_SOURCE if state["native"] else SHIM_SOURCE
    return _report(page, source, (state or {}).get("tools", []), state)


async def call_tool(page: Page, name: str, args: dict[str, Any] | None = None, timeout_s: float = 30.0) -> dict[str, Any]:
    """Run one tool the shim recorded and return its structuredContent (or its text content parsed as JSON)."""
    reply = await asyncio.wait_for(page.evaluate(CALL_JS, [name, args or {}]), timeout=timeout_s)
    if reply.get("missing"):
        raise WebMCPToolError(f"The page has no tool {name!r}.")
    if not reply["ok"]:
        raise WebMCPToolError(reply["error"])
    return unwrap(reply["result"])


class Tools:
    """A page's WebMCP tools for one run: native through CDP when the browser has it, else through the shim."""

    def __init__(self, page: Page):
        self.page = page
        self.native: dict[str, dict[str, Any]] = {}  # tool name -> CDP tool (with its frameId)
        self.responses: dict[str, dict[str, Any]] = {}  # invocationId -> WebMCP.toolResponded
        self.cdp: Any = None

    async def start(self) -> None:
        """Call before the first navigation. Without native WebMCP the CDP domain is missing and the shim is used."""
        try:
            self.cdp = await self.page.context.new_cdp_session(self.page)
            self.cdp.on("WebMCP.toolsAdded", self._added)
            self.cdp.on("WebMCP.toolsRemoved", self._removed)
            self.cdp.on("WebMCP.toolResponded", lambda e: self.responses.__setitem__(e["invocationId"], e))
            await self.cdp.send("WebMCP.enable")
        except PlaywrightError:
            self.cdp = None

    def _added(self, event: dict[str, Any]) -> None:
        for tool in event.get("tools", []):
            self.native[tool["name"]] = tool

    def _removed(self, event: dict[str, Any]) -> None:
        for tool in event.get("tools", []):
            self.native.pop(tool["name"], None)

    async def discover(self, timeout_s: float = 10.0) -> dict[str, Any]:
        deadline = time.monotonic() + timeout_s
        stable_since, count = time.monotonic(), -1
        while time.monotonic() < deadline:
            found = len(self.native) or len((await _shim_state(self.page) or {}).get("tools", []))
            now = time.monotonic()
            if found != count:
                count, stable_since = found, now
            elif found and now - stable_since >= SETTLE_S:
                break
            await self.page.wait_for_timeout(150)
        state = await _shim_state(self.page)
        if not self.native:
            return _report(self.page, None if state is None else NATIVE_SOURCE if state["native"] else SHIM_SOURCE,
                           (state or {}).get("tools", []), state)
        tools = [{"name": t["name"], "description": t.get("description") or "", "input_schema": _schema(t.get("inputSchema")),
                  "read_only": bool((t.get("annotations") or {}).get("readOnly")),
                  "consequential": bool((t.get("annotations") or {}).get("consequential")),
                  "untrusted_content": bool((t.get("annotations") or {}).get("untrustedContent"))}
                 for t in self.native.values()]
        return _report(self.page, NATIVE_SOURCE, tools, state)

    async def call(self, name: str, args: dict[str, Any] | None, timeout_s: float = 30.0) -> tuple[dict[str, Any], dict[str, Any]]:
        """(the tool's result, how it was called). Raises WebMCPToolError when the tool fails."""
        tool = self.native.get(name)
        if tool is None:
            return await call_tool(self.page, name, args, timeout_s), {"via": "shim"}
        sent = await self.cdp.send("WebMCP.invokeTool", {"frameId": tool["frameId"], "toolName": name, "input": args or {}})
        invocation = sent["invocationId"]
        deadline = time.monotonic() + timeout_s
        while invocation not in self.responses:
            if time.monotonic() > deadline:
                raise asyncio.TimeoutError
            await asyncio.sleep(0.05)
        reply = self.responses.pop(invocation)
        meta = {"via": "cdp", "invocation_id": invocation, "frame_id": tool["frameId"], "status": reply.get("status")}
        if reply.get("status") != "Completed":
            raise WebMCPToolError(_failure_text(reply))
        return unwrap(reply.get("output")), meta


def _schema(raw: Any) -> dict[str, Any]:
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except ValueError:
            return {}
    return raw if isinstance(raw, dict) else {}


def _failure_text(reply: dict[str, Any]) -> str:
    """Why a native call failed: errorText, else the thrown error's first line (CDP puts it in exception.description)."""
    thrown = ((reply.get("exception") or {}).get("description") or "").split("\n")[0].removeprefix("Error: ")
    return str(reply.get("errorText") or thrown or f"Tool call ended with status {reply.get('status')}")
