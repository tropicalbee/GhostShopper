"""Service worker requests, Kernel cleanup and the run time limit. All fakes: no real Kernel, no network."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from playwright.async_api import Error as PlaywrightError

from backend.app.agent import browser as browser_mod
from backend.app.agent.browser import BrowserSession
from backend.app.agent.llm import ChatModel
from backend.app.agent.loop import RunConfig, run_shopper
from backend.app.agent.recorder import load_run
from backend.app.agent.site import SiteError

pytestmark = pytest.mark.anyio

SW_ERROR = "Service Worker requests do not have an associated frame."


class FakeRoute:
    def __init__(self, fail: bool = False):
        self.fail = fail
        self.calls: list[tuple] = []

    async def continue_(self):
        self.calls.append(("continue",))
        if self.fail:
            raise PlaywrightError(f"Route.continue_: {SW_ERROR}")

    async def abort(self, code="failed"):
        self.calls.append(("abort", code))
        if self.fail:
            raise PlaywrightError(f"Route.abort: {SW_ERROR}")


class FakeRequest:
    def __init__(self, url, service_worker=False, frame_raises=False, resource_type="fetch", navigation=False):
        self.url = url
        self.resource_type = resource_type
        self._sw = service_worker
        self._frame_raises = frame_raises
        self._nav = navigation

    @property
    def service_worker(self):
        return object() if self._sw else None

    @property
    def frame(self):
        if self._frame_raises:
            raise PlaywrightError(SW_ERROR)
        return SimpleNamespace(parent_frame=None)

    def is_navigation_request(self):
        return self._nav


@pytest.fixture
def session(monkeypatch):
    async def fake_check_host(url, allow_private):
        if "10.0.0.1" in url:
            raise SiteError("private address")

    monkeypatch.setattr(browser_mod, "check_host", fake_check_host)
    politeness = MagicMock()
    politeness.allowed = AsyncMock(return_value=True)
    politeness.wait_turn = AsyncMock()
    return BrowserSession(politeness=politeness, allow_private=False)


async def test_service_worker_request_is_continued_without_raising(session):
    route = FakeRoute()
    await session._guard(route, FakeRequest("https://shop.example/sw.js", frame_raises=True, service_worker=True))
    assert route.calls == [("continue",)]
    session.politeness.allowed.assert_not_called()  # not a page load


async def test_service_worker_navigation_is_not_a_main_load(session):
    route = FakeRoute()
    await session._guard(route, FakeRequest("https://shop.example/", frame_raises=True, resource_type="document",
                                            navigation=True))
    assert route.calls == [("continue",)]
    session.politeness.allowed.assert_not_called()


async def test_private_host_service_worker_request_is_aborted(session):
    route = FakeRoute()
    await session._guard(route, FakeRequest("http://10.0.0.1/x", frame_raises=True, service_worker=True))
    assert route.calls == [("abort", "blockedbyclient")]
    assert session.refused == {}  # only main-frame loads are recorded as refused pages


async def test_unresolvable_route_never_raises(session):
    for req in (FakeRequest("https://shop.example/a", frame_raises=True), FakeRequest("http://10.0.0.1/b", service_worker=True)):
        await session._guard(FakeRoute(fail=True), req)  # continue_/abort raise: swallowed, logged once


async def test_normal_main_load_still_follows_politeness(session):
    route = FakeRoute()
    await session._guard(route, FakeRequest("https://shop.example/p", resource_type="document", navigation=True))
    session.politeness.allowed.assert_awaited_once()
    session.politeness.wait_turn.assert_awaited_once()
    assert route.calls == [("continue",)]

    session.politeness.allowed.return_value = False
    route = FakeRoute()
    await session._guard(route, FakeRequest("https://shop.example/q", resource_type="document", navigation=True))
    assert route.calls == [("abort", "blockedbyclient")]
    assert "robots.txt" in session.refused["https://shop.example/q"]


async def test_normal_private_main_load_is_refused_and_recorded(session):
    route = FakeRoute()
    await session._guard(route, FakeRequest("http://10.0.0.1/admin", resource_type="document", navigation=True))
    assert route.calls == [("abort", "blockedbyclient")]
    assert session.refused["http://10.0.0.1/admin"] == "private address"


async def test_data_urls_are_continued(session):
    route = FakeRoute()
    await session._guard(route, FakeRequest("data:text/plain,hi"))
    assert route.calls == [("continue",)]


def _fake_playwright(monkeypatch, cdp_fails=False):
    """async_playwright() whose chromium launches/connects fakes. Returns the fakes for assertions."""
    page = MagicMock(url="about:blank")
    page.set_viewport_size = AsyncMock()
    page.route = AsyncMock()
    cdp = MagicMock()
    cdp.send = AsyncMock(side_effect=PlaywrightError("no CDP") if cdp_fails else None)
    context = MagicMock(pages=[page])
    context.route = AsyncMock()
    context.close = AsyncMock()
    context.new_page = AsyncMock(return_value=page)
    context.new_cdp_session = AsyncMock(return_value=cdp)
    browser = MagicMock(contexts=[context])
    browser.close = AsyncMock()
    browser.new_context = AsyncMock(return_value=context)
    browser.new_page = AsyncMock(return_value=page)
    chromium = MagicMock()
    chromium.connect_over_cdp = AsyncMock(return_value=browser)
    chromium.launch = AsyncMock(return_value=browser)
    pw = MagicMock(chromium=chromium)
    pw.stop = AsyncMock()
    monkeypatch.setattr(browser_mod, "async_playwright", lambda: SimpleNamespace(start=AsyncMock(return_value=pw)))
    return SimpleNamespace(pw=pw, browser=browser, context=context, page=page, cdp=cdp, chromium=chromium)


class FakeKernel:
    def __init__(self, delete_fails=False):
        self.created: list[dict] = []
        self.deleted: list[str] = []
        self.delete_fails = delete_fails

    async def create(self, *, headless, timeout_seconds):
        self.created.append({"headless": headless, "timeout_seconds": timeout_seconds})
        return {"session_id": "sess-1", "cdp_ws_url": "ws://fake", "browser_live_view_url": None}

    async def delete(self, session_id):
        self.deleted.append(session_id)
        if self.delete_fails:
            raise RuntimeError("kernel down")


def test_kernel_timeout_default_is_300():
    from inspect import signature

    assert signature(BrowserSession).parameters["kernel_timeout_s"].default == 300


async def test_local_context_blocks_service_workers(monkeypatch):
    fakes = _fake_playwright(monkeypatch)
    async with BrowserSession(provider="local", politeness=MagicMock()):
        pass
    assert fakes.browser.new_context.await_args.kwargs["service_workers"] == "block"
    fakes.context.route.assert_awaited_once()


async def test_kernel_bypasses_service_workers_and_deletes_session(monkeypatch):
    fakes, kernel = _fake_playwright(monkeypatch), FakeKernel()
    async with BrowserSession(kernel=kernel, politeness=MagicMock()):
        fakes.context.new_cdp_session.assert_awaited_once_with(fakes.page)
        fakes.cdp.send.assert_awaited_once_with("Network.setBypassServiceWorker", {"bypass": True})
        assert fakes.context.on.call_args.args[0] == "page"  # popups get the same treatment
    assert kernel.created[0]["timeout_seconds"] == 300
    assert kernel.deleted == ["sess-1"]


async def test_kernel_bypass_failure_is_not_fatal(monkeypatch):
    _fake_playwright(monkeypatch, cdp_fails=True)
    kernel = FakeKernel()
    async with BrowserSession(kernel=kernel, politeness=MagicMock()) as s:
        assert s.page is not None
    assert kernel.deleted == ["sess-1"]


async def test_kernel_session_deleted_when_body_raises(monkeypatch):
    _fake_playwright(monkeypatch)
    kernel = FakeKernel()
    with pytest.raises(ValueError, match="boom"):
        async with BrowserSession(kernel=kernel):
            raise ValueError("boom")
    assert kernel.deleted == ["sess-1"]


async def test_kernel_delete_failure_does_not_mask_the_run_error(monkeypatch):
    fakes = _fake_playwright(monkeypatch)
    kernel = FakeKernel(delete_fails=True)
    with pytest.raises(ValueError, match="boom"):
        async with BrowserSession(kernel=kernel):
            raise ValueError("boom")
    fakes.pw.stop.assert_awaited_once()  # cleanup carried on past the failed delete


class HangingLLM(ChatModel):
    kind, model = "mock", None

    async def complete(self, messages, tools):
        await asyncio.sleep(60)


async def test_stuck_run_times_out_and_kernel_session_is_deleted(monkeypatch, tmp_path):
    _fake_playwright(monkeypatch)
    kernel = FakeKernel()
    cfg = RunConfig(store_url="https://shop.example/", db_path=tmp_path / "t.db", runs_dir=tmp_path / "runs",
                    live=True, max_run_s=0.3, llm_timeout_s=60,
                    session_factory=lambda: BrowserSession(kernel=kernel, politeness=MagicMock()))
    run = load_run(cfg.db_path, await run_shopper(cfg, HangingLLM()))
    assert run["status"] == "error" and "time limit" in run["error"]
    assert kernel.deleted == ["sess-1"]


async def test_cancelled_run_deletes_kernel_session(monkeypatch, tmp_path):
    _fake_playwright(monkeypatch)
    kernel = FakeKernel()
    cfg = RunConfig(store_url="https://shop.example/", db_path=tmp_path / "t.db", runs_dir=tmp_path / "runs",
                    live=True, llm_timeout_s=60,
                    session_factory=lambda: BrowserSession(kernel=kernel, politeness=MagicMock()))
    task = asyncio.create_task(run_shopper(cfg, HangingLLM()))
    await asyncio.sleep(0.3)  # the run is now waiting on the LLM, as Ctrl+C would find it
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert kernel.deleted == ["sess-1"]
