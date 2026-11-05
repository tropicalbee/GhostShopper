"""GhostShopper API. Also serves the dashboard at / and the demo store at /store."""

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from store import catalog
from store.app import create_store_app

from . import db
from .agent.llm import groq_configured
from .config import PAYPAL_SDK_URL, Settings, get_settings
from .market import MarketError, market_check
from .orders import router as orders_router
from .owner import COOKIE, MAX_AGE_S, hash_token, new_token, valid_token
from .paypal import PayPalClient
from .paypal_mock import MOCK_CLIENT_ID, MOCK_SDK_PATH, FakePayPalClient, mock_router
from .ratelimit import RateLimiter, rate_limit
from .runs import router as runs_router
from .scoring import CHECKS, RULES_VERSION, STAGES

log = logging.getLogger(__name__)

# The dashboard only loads its own files. AG Grid and Recharts set inline styles, hence 'unsafe-inline' for
# styles only; scripts stay 'self'. Screenshots are same-origin images; downloads use blob: URLs.
DASHBOARD_CSP = ("default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; "
                 "font-src 'self' data:; connect-src 'self'; object-src 'none'; base-uri 'none'; form-action 'self'; "
                 "frame-ancestors 'none'")


def create_app(settings: Settings | None = None, paypal: PayPalClient | FakePayPalClient | None = None) -> FastAPI:
    settings = settings or get_settings()
    db.init_db(settings.database_path)
    mock = settings.paypal_mode == "mock"
    if mock and paypal is None:
        paypal = FakePayPalClient()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        purged = db.purge_old_runs(settings.database_path, settings.runs_dir, settings.retention_days)
        if purged:
            log.info("Retention: deleted %d check(s) older than %d days", len(purged), settings.retention_days)
        owns_client = paypal is None and settings.paypal_configured
        if owns_client:
            app.state.paypal = PayPalClient(settings.paypal_client_id, settings.paypal_client_secret)
        yield
        if owns_client:
            await app.state.paypal.aclose()

    app = FastAPI(title="GhostShopper", version="0.1.0", lifespan=lifespan,
                  docs_url="/api/docs" if settings.dev_options else None,
                  redoc_url=None, openapi_url="/api/openapi.json" if settings.dev_options else None)
    app.state.settings = settings
    app.state.paypal = paypal
    app.state.run_lock = asyncio.Lock()
    app.state.run_tasks = set()
    app.state.run_limiter = RateLimiter(*settings.run_rate_limit)
    app.state.api_limiter = RateLimiter(*settings.api_rate_limit)

    @app.middleware("http")
    async def owner_and_headers(request: Request, call_next):
        token = request.cookies.get(COOKIE)
        fresh = not valid_token(token)
        if fresh:
            token = new_token()
        request.state.owner = hash_token(token)
        response = await call_next(request)
        if fresh:
            response.set_cookie(COOKIE, token, max_age=MAX_AGE_S, httponly=True, samesite="lax",
                                secure=settings.https, path="/")
        h = response.headers
        h.setdefault("X-Content-Type-Options", "nosniff")
        h.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        h.setdefault("X-Frame-Options", "DENY")
        if settings.https:
            h.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
        return response

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
            "demo_admin_open": settings.dev_options,
            "retention_days": settings.retention_days,
        }

    @app.get("/api/rubric")
    def rubric():
        """Points per stage of the shopper's path, straight from the scoring rules (the Home walkthrough)."""
        return {"rules_version": RULES_VERSION, "stages": [
            {"key": s, "points": sum(c.points for c in CHECKS.values() if c.stage == s),
             "checks": sum(1 for c in CHECKS.values() if c.stage == s)} for s in STAGES]}

    @app.get("/api/market/{sku}")
    async def market(sku: str, request: Request):
        """Informational market check (Channel3 live, or recorded fixtures). Never part of the score."""
        product = catalog.get_by_sku(sku)
        if product is None:
            raise HTTPException(status_code=404, detail={"error": "UNKNOWN_SKU", "message": "No such product."})
        rate_limit(request, "api_limiter")
        try:
            return await market_check(product)
        except MarketError as exc:
            log.warning("Market check failed: %s", exc)
            raise HTTPException(status_code=502, detail={"error": "MARKET_CHECK_FAILED",
                                                          "message": "The market check isn't available right now."}) from exc

    index = settings.frontend_dist / "index.html"
    if index.is_file():
        app.mount("/assets", StaticFiles(directory=settings.frontend_dist / "assets", check_dir=False), name="assets")

    @app.get("/", include_in_schema=False)
    def dashboard():
        if not index.is_file():
            return JSONResponse(status_code=503, content={
                "error": "FRONTEND_NOT_BUILT",
                "message": "The dashboard isn't built. Run `npm run build` in frontend/, or use `npm run dev`."})
        return FileResponse(index, headers={"Content-Security-Policy": DASHBOARD_CSP, "Cache-Control": "no-cache"})

    app.mount(
        "/store",
        create_store_app(
            db_path=settings.database_path,
            paypal_client_id=MOCK_CLIENT_ID if mock else settings.paypal_client_id,
            paypal_sdk_url=MOCK_SDK_PATH if mock else PAYPAL_SDK_URL,
            admin_open=settings.dev_options,
            admin_token=settings.demo_admin_token,
        ),
    )
    return app


app = create_app()
