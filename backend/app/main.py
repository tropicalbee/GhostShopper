"""GhostShopper API. Also serves the demo store at /store."""

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse

from store.app import create_store_app

from . import db
from .config import PAYPAL_SDK_URL, Settings, get_settings
from .orders import router as orders_router
from .paypal import PayPalClient


def create_app(settings: Settings | None = None, paypal: PayPalClient | None = None) -> FastAPI:
    settings = settings or get_settings()
    db.init_db(settings.database_path)

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

    app.include_router(orders_router)

    @app.get("/api/health")
    def health(request: Request):
        return {
            "status": "ok",
            "paypal_configured": request.app.state.paypal is not None,
            "paypal_env": "sandbox",
        }

    @app.get("/", include_in_schema=False)
    def root():
        return RedirectResponse("/store/")

    app.mount(
        "/store",
        create_store_app(
            db_path=settings.database_path,
            paypal_client_id=settings.paypal_client_id,
            paypal_sdk_url=PAYPAL_SDK_URL,
        ),
    )
    return app


app = create_app()
