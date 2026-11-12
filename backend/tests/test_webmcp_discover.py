"""Tool discovery and calls on a local fixture page that registers the four shopping.* tools (no network)."""

from pathlib import Path

import pytest
from playwright.async_api import async_playwright

from backend.app.webmcp.discover import NATIVE_SOURCE, SHIM_SOURCE, WebMCPToolError, call_tool, discover, install_shim
from backend.app.webmcp.tools import SHOPPING_TOOLS

from .test_agent_e2e import requires_browser

pytestmark = pytest.mark.anyio

FIXTURE = (Path(__file__).parent / "fixtures" / "webmcp" / "store.html").as_uri()


@pytest.fixture
async def context():
    async with async_playwright() as pw:
        browser = await pw.chromium.launch()
        ctx = await browser.new_context()
        # The fixture names scripts on hosts we never contact: keep the page offline.
        await ctx.route("http://**/*", lambda route: route.abort())
        await ctx.route("https://**/*", lambda route: route.abort())
        yield ctx
        await browser.close()


@requires_browser
async def test_discovers_the_four_tools_through_the_shim(context):
    await install_shim(context)
    page = await context.new_page()
    await page.goto(FIXTURE)
    found = await discover(page)
    assert found["source"] == SHIM_SOURCE
    assert [t["name"] for t in found["tools"]] == sorted(SHOPPING_TOOLS)
    by_name = {t["name"]: t for t in found["tools"]}
    assert by_name["shopping.searchProducts"]["read_only"] and not by_name["shopping.initiateCheckout"]["read_only"]
    assert by_name["shopping.getProduct"]["input_schema"]["type"] == "object"
    assert found["context"]["storeId"] == "fixture"
    assert found["paypal_sdk_v6"] and found["webmcp_script"]


@requires_browser
async def test_a_native_model_context_is_kept_and_reported_as_native(context):
    await context.add_init_script(script="navigator.modelContext = {registerTool(){ return 'native'; }, provideContext(){}};")
    await install_shim(context)
    page = await context.new_page()
    await page.goto(FIXTURE)
    found = await discover(page)
    assert found["source"] == NATIVE_SOURCE and len(found["tools"]) == 4
    assert await page.evaluate("navigator.modelContext.registerTool({name: 'x'})") == "native"


@requires_browser
async def test_a_page_without_tools_reports_none_after_the_timeout(context):
    await install_shim(context)
    page = await context.new_page()
    await page.goto("about:blank")
    found = await discover(page, timeout_s=0.5)
    assert found["tools"] == [] and not found["paypal_sdk_v6"] and not found["webmcp_script"]


@requires_browser
async def test_call_tool_returns_structured_content_and_raises_on_errors(context):
    await install_shim(context)
    page = await context.new_page()
    await page.goto(FIXTURE)
    await discover(page)
    assert await call_tool(page, "shopping.getProduct", {"product_id": "A"}) == {
        "tool": "shopping.getProduct", "echo": {"product_id": "A"}}
    with pytest.raises(WebMCPToolError, match="fixture failure"):
        await call_tool(page, "shopping.searchProducts", {"fail": True})
    with pytest.raises(WebMCPToolError, match="no tool"):
        await call_tool(page, "shopping.nope")


@requires_browser
async def test_native_webmcp_is_discovered_and_called_through_the_cdp_domain(tmp_path):
    """Chromium with --enable-features=WebMCP: Fernhill's adapter registers on document.modelContext, the tools arrive
    as WebMCP.toolsAdded, and WebMCP.invokeTool answers with WebMCP.toolResponded."""
    from backend.app.config import Settings
    from backend.app.main import create_app
    from backend.app.webmcp.discover import LAUNCH_ARGS, Tools

    from .live_server import LiveServer

    settings = Settings(paypal_client_id="", paypal_client_secret="", database_path=tmp_path / "n.db",
                        app_base_url="http://unused", paypal_mode="mock", dev_options=True)
    with LiveServer(create_app(settings)) as srv:
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(args=LAUNCH_ARGS)
            page = await (await browser.new_context()).new_page()
            tools = Tools(page)
            await tools.start()
            await page.goto(f"{srv.url}/store/")
            if not await page.evaluate("!!document.modelContext && !!document.modelContext.registerTool"):
                await browser.close()
                pytest.skip("this Chromium has no native WebMCP behind --enable-features=WebMCP")
            found = await tools.discover()
            assert found["source"] == NATIVE_SOURCE and set(tools.native) == set(SHOPPING_TOOLS)
            by_name = {t["name"]: t for t in found["tools"]}
            assert by_name["shopping.searchProducts"]["read_only"] and not by_name["shopping.initiateCheckout"]["read_only"]
            result, meta = await tools.call("shopping.searchProducts", {"query": "speckled mug"})
            assert result["products"][0]["product_id"] == "FH-MUG-01"
            assert meta["via"] == "cdp" and meta["status"] == "Completed" and meta["invocation_id"] and meta["frame_id"]
            with pytest.raises(WebMCPToolError):
                await tools.call("shopping.getProduct", {"product_id": "NOPE"})
            await browser.close()
