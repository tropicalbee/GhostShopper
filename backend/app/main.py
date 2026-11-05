"""GhostShopper API. Also serves the demo store at /store."""

import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import RedirectResponse

from store import catalog
from store.app import create_store_app

from . import db
from .agent.llm import groq_configured
from .config import PAYPAL_SDK_URL, Settings, get_settings
from .market import MarketError, market_check
from .orders import router as orders_router
from .paypal import PayPalClient
from .paypal_mock import MOCK_CLIENT_ID, MOCK_SDK_PATH, FakePayPalClient, mock_router
from .runs import router as runs_router


def create_app(settings: Settings | None = None, paypal: PayPalClient | FakePayPalClient | None = None) -> FastAPI:
    settings = settings or get_settings()
    db.init_db(settings.database_path)
    mock = settings.paypal_mode == "mock"
    if mock and paypal is None:
        paypal = FakePayPalClient()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        owns_client = paypal is None and settings.paypal_configured
        if owns_client:
            app.state.paypal = PayPalClient(settings.paypal_client_id, settings.paypal_client_secret)
        yield
        if owns_client:
            await app.state.paypal.aclose()

    app = FastAPI(title="GhostShopper", version="0.1.0", lifespan=lifespan)
    app.state.settings = settings
    app.state.paypal = paypal
    app.state.run_lock = asyncio.Lock()
    app.state.run_tasks = set()

    app.include_router(orders_router)
    app.include_router(runs_router)
    if mock:
        app.include_router(mock_router(paypal))

    @app.get("/api/health")
    def health(request: Request):
        return {
            "status": "ok",
            "paypal_configured": request.app.state.paypal is not None,
            "paypal_env": "sandbox",
            "paypal_mode": settings.paypal_mode,
            "groq_configured": groq_configured(),
        }

    @app.get("/api/market/{sku}")
    async def market(sku: str):
        """Informational market check (Channel3 live, or recorded fixtures). Never part of the score."""
        product = catalog.get_by_sku(sku)
        if product is None:
            raise HTTPException(status_code=404, detail={"error": "UNKNOWN_SKU", "message": sku})
        try:
            return await market_check(product)
        except MarketError as exc:
            raise HTTPException(status_code=502, detail={"error": "MARKET_CHECK_FAILED", "message": str(exc)}) from exc

    @app.get("/", include_in_schema=False)
    def root():
        return RedirectResponse("/store/")

    app.mount(
        "/store",
        create_store_app(
            db_path=settings.database_path,
            paypal_client_id=MOCK_CLIENT_ID if mock else settings.paypal_client_id,
            paypal_sdk_url=MOCK_SDK_PATH if mock else PAYPAL_SDK_URL,
        ),
    )
    return app


app = create_app()
