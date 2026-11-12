"""GhostShopper API. Also serves the dashboard at / and the demo store at /store."""

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from store import catalog
from store.app import create_store_app

from . import db
from .agent.llm import live_llm_configured
from .agent.service import real_checkout_missing
from .catalog_readiness import router as catalog_router
from .config import PAYPAL_MODES, PAYPAL_SDK_URL, Settings, get_settings, vision_model
from .examples import load_examples
from .ledger import router as ledger_router
from .market import MarketError, market_check
from .orders import router as orders_router
from .owner import COOKIE, MAX_AGE_S, hash_token, new_token, valid_token
from .paypal import PayPalClient
from .paypal_mock import MOCK_CLIENT_ID, MOCK_SDK_PATH, FakePayPalClient, mock_router
from .ratelimit import RateLimiter, client_ip, rate_limit
from .runs import presenter_unlocked
from .runs import router as runs_router
from .scoring import CHECKS, RULES_VERSION, STAGES
from .webmcp.rpc import router as webmcp_router

log = logging.getLogger(__name__)

# The dashboard only loads its own files. AG Grid and Recharts set inline styles, hence 'unsafe-inline' for
# styles only; scripts stay 'self'. Screenshots are same-origin images; downloads use blob: URLs.
DASHBOARD_CSP = ("default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; "
                 "font-src 'self' data:; connect-src 'self'; object-src 'none'; base-uri 'none'; form-action 'self'; "
                 "frame-ancestors 'none'")


def _cache_policy(path: str, status: int) -> str | None:
    """Cache-Control for responses that don't set their own. The dashboard index and the screenshot endpoint
    do; the demo store (HTML) is left alone."""
    if path.startswith("/assets/"):
        return "public, max-age=31536000, immutable" if status == 200 else None  # build output is content-hashed
    if path == "/api/rubric":
        return "public, max-age=3600"
    if path.startswith("/api/"):
        return "private, no-store"  # one browser's private data
    return None


def create_app(settings: Settings | None = None, paypal: PayPalClient | FakePayPalClient | None = None) -> FastAPI:
    settings = settings or get_settings()
    db.init_db(settings.database_path)
    # Both modes live side by side: PAYPAL_MODE is the default, and a run may ask for the other (runs.py). The mock
    # is always there; the sandbox client only exists when its credentials do. app.state.paypal_active is the mode
    # the order endpoints and the store use right now (a run sets it for its duration, runs are one at a time).
    clients: dict[str, PayPalClient | FakePayPalClient] = {}
    if paypal is not None:
        clients[settings.paypal_mode] = paypal
    clients.setdefault("mock", FakePayPalClient())

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        purged = db.purge_old_runs(settings.database_path, settings.runs_dir, settings.retention_days)
        if purged:
            log.info("Retention: deleted %d check(s) older than %d days", len(purged), settings.retention_days)
        if settings.example_runs:
            added = load_examples(settings.database_path, settings.runs_dir)
            if added:
                log.info("Examples: loaded %d bundled check(s) as runs %s", len(added), added)
        owns_client = "sandbox" not in clients and settings.paypal_configured
        if owns_client:
            clients["sandbox"] = PayPalClient(settings.paypal_client_id, settings.paypal_client_secret)
        if settings.vault_token_id and "sandbox" in clients:
            # A fresh database (a new deploy) has no saved buyer; seed the one from the environment. Never logged.
            saved = db.latest_vault_token(settings.database_path, "sandbox")
            if saved is None or saved["payment_token_id"] != settings.vault_token_id:
                db.save_vault_token(settings.database_path, paypal_mode="sandbox",
                                    payment_token_id=settings.vault_token_id, customer_id=settings.vault_customer_id or None)
                log.info("Vault: saved the sandbox buyer from the environment")
        yield
        if owns_client:
            await clients.pop("sandbox").aclose()

    app = FastAPI(title="GhostShopper", version="0.1.0", lifespan=lifespan,
                  docs_url="/api/docs" if settings.dev_options else None,
                  redoc_url=None, openapi_url="/api/openapi.json" if settings.dev_options else None)
    app.state.settings = settings
    app.state.paypal_clients = clients
    app.state.paypal_active = settings.paypal_mode
    app.state.run_lock = asyncio.Lock()
    app.state.run_tasks = set()
    app.state.run_limiter = RateLimiter(*settings.run_rate_limit)
    app.state.api_limiter = RateLimiter(*settings.api_rate_limit)
    app.state.daily_caps = {name: RateLimiter(cap, 86400) for name, cap in (
        ("runs", settings.run_daily_cap), ("market", settings.market_daily_cap), ("orders", settings.order_daily_cap),
        ("catalog", settings.catalog_daily_cap))}
    unlock_limiter = RateLimiter(*settings.unlock_rate_limit)

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
        cache = _cache_policy(request.url.path, response.status_code)
        if "cache-control" not in h:
            # A response that hands out a fresh owner cookie must never be stored by a shared cache, whatever its path.
            if fresh:
                h["Cache-Control"] = cache.replace("public", "private") if cache else "private, no-store"
            elif cache:
                h["Cache-Control"] = cache
        h.setdefault("X-Content-Type-Options", "nosniff")
        h.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        h.setdefault("X-Frame-Options", "DENY")
        if settings.https:
            h.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
        return response

    app.add_middleware(GZipMiddleware, minimum_size=1000)  # added last = outermost: wraps the headers above

    app.include_router(orders_router)
    app.include_router(runs_router)
    app.include_router(ledger_router)
    app.include_router(catalog_router)
    app.include_router(webmcp_router)  # before the /store mount below, which would otherwise answer /store/webmcp/rpc
    app.include_router(mock_router(clients["mock"]))

    @app.get("/api/health")
    def health(request: Request):
        real_missing = real_checkout_missing(settings.paypal_configured or "sandbox" in clients)
        return {
            "status": "ok",
            "paypal_configured": settings.paypal_mode in clients,
            "paypal_env": "sandbox",
            "paypal_mode": settings.paypal_mode,
            # Whether a run may ask for a real PayPal sandbox purchase, and what is missing if not.
            "real_checkout_available": not real_missing,
            "real_checkout_missing": real_missing,
            "vault_ready": db.latest_vault_token(settings.database_path, "sandbox") is not None,  # a saved sandbox buyer
            "presenter_unlocked": presenter_unlocked(request),  # this browser may change the store's flaws
            "llm_configured": live_llm_configured(),
            "vision_available": live_llm_configured() and bool(vision_model()),  # the shopper can be given eyes
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
        rate_limit(request, "api_limiter", "market")
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

    # One store app per PayPal mode (the checkout page embeds the SDK URL). Both read the same database, so the
    # flaws are shared; each request goes to the app for the mode that is active.
    stores = {
        mode: create_store_app(
            db_path=settings.database_path,
            paypal_client_id=MOCK_CLIENT_ID if mode == "mock" else settings.paypal_client_id,
            paypal_sdk_url=MOCK_SDK_PATH if mode == "mock" else PAYPAL_SDK_URL,
            admin_open=settings.dev_options,
            admin_token=settings.demo_admin_token,
            unlock_allowed=lambda request: unlock_limiter.hit(client_ip(request, settings.trusted_proxy_hops)),
        )
        for mode in PAYPAL_MODES
    }

    async def store(scope, receive, send):
        await stores[app.state.paypal_active](scope, receive, send)

    app.mount("/store", store)
    return app


app = create_app()
