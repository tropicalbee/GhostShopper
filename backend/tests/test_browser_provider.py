"""Browser provider switch: local Playwright (default) or Kernel over CDP. Tested locally only:
a local Chromium with a CDP port plays Kernel's remote browser, and Kernel's REST API is faked."""

import json
import socket

import httpx
import pytest

from backend.app.agent.browser import KERNEL_API_BASE, BrowserConfigError, BrowserSession, KernelBrowsers, resolve_provider
from backend.app.agent.llm import ReplayLLM, resolve_cassette
from backend.app.agent.loop import RunConfig, run_shopper
from backend.app.agent.recorder import load_run
from backend.app.agent.service import RunConfigError, RunRequest, apply_flaws, prepare

from .test_agent_e2e import requires_browser, server  # noqa: F401  (fixture)


def test_local_is_the_default(monkeypatch):
    monkeypatch.delenv("BROWSER_PROVIDER", raising=False)
    assert resolve_provider() == "local"


def test_kernel_needs_its_api_key(monkeypatch):
    monkeypatch.delenv("KERNEL_API_KEY", raising=False)
    with pytest.raises(BrowserConfigError, match="KERNEL_API_KEY"):
        resolve_provider("kernel")
    monkeypatch.setenv("BROWSER_PROVIDER", "kernel")
    with pytest.raises(RunConfigError, match="KERNEL_API_KEY"):
        prepare(RunRequest(llm="mock", cassette="day2_flaws_off"), "http://x/store/", None)  # type: ignore[arg-type]
    monkeypatch.setenv("KERNEL_API_KEY", "k-1")
    assert resolve_provider() == "kernel"


def test_unknown_provider_is_rejected():
    with pytest.raises(BrowserConfigError, match="browserbase"):
        resolve_provider("browserbase")


@requires_browser
@pytest.mark.anyio
async def test_kernel_provider_runs_the_same_agent_over_cdp(server, tmp_path):  # noqa: F811
    from playwright.async_api import async_playwright

    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    calls = []

    def kernel_api(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content) if request.content else None
        calls.append((request.method, request.url.path, request.headers.get("authorization"), body))
        if request.method == "POST" and request.url.path == "/browsers":
            return httpx.Response(200, json={"session_id": "sess-1", "cdp_ws_url": f"http://127.0.0.1:{port}",
                                             "browser_live_view_url": "https://live.example/sess-1"})
        if request.method == "DELETE":
            return httpx.Response(204)
        return httpx.Response(404)

    kernel = KernelBrowsers("k-1", http=httpx.AsyncClient(
        base_url=KERNEL_API_BASE, headers={"Authorization": "Bearer k-1"}, transport=httpx.MockTransport(kernel_api)))
    store_url = f"{server.url}/store/"
    await apply_flaws(store_url, "off")
    async with async_playwright() as pw:
        remote = await pw.chromium.launch(args=[f"--remote-debugging-port={port}"])  # stands in for Kernel's VM
        try:
            cfg = RunConfig(store_url=store_url, db_path=server.db_path, runs_dir=server.runs_dir,
                            session_factory=lambda: BrowserSession(headless=True, kernel=kernel))
            run = load_run(server.db_path, await run_shopper(cfg, ReplayLLM(resolve_cassette("day2_flaws_off"))))
        finally:
            await remote.close()

    assert run["browser"] == "kernel"
    assert run["status"] == "completed" and run["score"]["total"] == 80  # same result as the local run
    assert calls[0][:3] == ("POST", "/browsers", "Bearer k-1")
    assert calls[0][3]["stealth"] is False  # never Kernel's CAPTCHA solver
    assert calls[-1][:2] == ("DELETE", "/browsers/sess-1")  # session always cleaned up
