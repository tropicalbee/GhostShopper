"""Fernhill Ceramics: the demo merchant store, with toggleable agent-readiness flaws.

Mounted by the backend at /store. Checkout calls the backend's /api/paypal endpoints.
"""

import hashlib
import hmac
import json
from pathlib import Path
from typing import Any, Callable

from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from . import catalog
from .flaws import CLASSIC_FLAWS, FLAWS, FlawStore
from .orders import STATUS_LABELS, StoreOrders
from .price_image import render_price_svg, token_for

HERE = Path(__file__).parent
STORE_NAME = "Fernhill Ceramics"
DETAILS_COOKIE = "fh_details"
COOKIE_CONSENT = "fh_cookies"
ADMIN_COOKIE = "fh_admin"
ADMIN_COOKIE_CONTEXT = b"ghostshopper-admin-cookie-v1"
REFERRAL_OPTIONS = ("Instagram", "A friend", "Craft fair", "Search engine", "Other")


def admin_cookie_value(token: str) -> str:
    """What the unlock cookie carries: an HMAC of the token, so the cookie never holds the token itself."""
    return hmac.new(token.encode(), ADMIN_COOKIE_CONTEXT, hashlib.sha256).hexdigest()


def has_admin_cookie(request: Request, token: str) -> bool:
    supplied = request.cookies.get(ADMIN_COOKIE) or ""
    return bool(token) and hmac.compare_digest(supplied.encode(), admin_cookie_value(token).encode())


class FlawUpdate(BaseModel):
    flaws: dict[str, bool]


def create_store_app(*, db_path: Path, paypal_client_id: str, paypal_sdk_url: str, admin_open: bool = True,
                     admin_token: str = "", unlock_allowed: Callable[[Request], bool] | None = None) -> FastAPI:
    """admin_open: the settings page is open to anyone (local development). Otherwise it needs admin_token,
    entered once in the unlock form (which sets an httpOnly cookie) or sent as an X-Admin-Token header. A token in
    the URL is not accepted: it would end up in access logs and browser history. unlock_allowed (optional) is asked
    before each unlock attempt and returns False once the caller has tried too often."""
    app = FastAPI(title=STORE_NAME, docs_url=None, redoc_url=None, openapi_url=None)
    flaw_store = FlawStore(db_path)
    store_orders = StoreOrders(db_path)
    templates = Jinja2Templates(directory=HERE / "templates")
    # Cache-busting version for the stylesheet: changes whenever style.css changes.
    css_version = hashlib.sha256((HERE / "static" / "style.css").read_bytes()).hexdigest()[:10]
    price_tokens = {}
    for p in catalog.load_products():
        for amount in (p.price, p.price + catalog.PRICE_MISMATCH_SURCHARGE):
            price_tokens[token_for(p.sku, f"{amount:.2f}")] = f"{amount:.2f}"

    app.mount("/static", StaticFiles(directory=HERE / "static"), name="static")

    def render(request: Request, name: str, status_code: int = 200, **ctx: Any) -> HTMLResponse:
        base = request.scope.get("root_path", "")
        return templates.TemplateResponse(
            request,
            name,
            {
                "base": base,
                "origin": f"{request.url.scheme}://{request.url.netloc}",
                "store_name": STORE_NAME,
                "flaws": flaw_store.get_all(),
                "price_token": token_for,
                "categories": catalog.CATEGORIES,
                "css_version": css_version,
                **ctx,
            },
            status_code=status_code,
        )

    def checkout_entry(request: Request, product: catalog.Product) -> str:
        base = request.scope.get("root_path", "")
        step = "checkout/details" if flaw_store.get_all()["extra_checkout_step"] else "checkout"
        return f"{base}/{step}?sku={product.sku}"

    def require_product(sku: str) -> catalog.Product:
        product = catalog.get_by_sku(sku)
        if product is None:
            raise HTTPException(status_code=404, detail="Product not found")
        return product

    @app.get("/", response_class=HTMLResponse)
    def index(request: Request, category: str = ""):
        products = catalog.load_products()
        if category not in catalog.CATEGORIES:
            category = ""
        shown = [p for p in products if p.category == category] if category else list(products)
        return render(request, "index.html", products=shown, all_products=products, category=category)

    @app.get("/products/{slug}", response_class=HTMLResponse)
    def product_page(request: Request, slug: str):
        product = catalog.get_by_slug(slug)
        if product is None:
            raise HTTPException(status_code=404, detail="Product not found")
        products = catalog.load_products()
        next_product = products[(products.index(product) + 1) % len(products)]
        # Recommend only items that can be bought: a "Sold out" badge here would read as this product's stock.
        others = [p for p in products if p.sku != product.sku and p.in_stock]
        related = ([p for p in others if p.category == product.category] +
                   [p for p in others if p.category != product.category])[:4]
        flaws = flaw_store.get_all()
        listed_out = (not product.in_stock) or flaws["oos_buyable"]
        json_ld = {
            "@context": "https://schema.org",
            "@type": "Product",
            "name": product.name,
            "sku": product.sku,
            "description": product.description,
            "image": f"{request.url.scheme}://{request.url.netloc}{request.scope.get('root_path', '')}/static/img/{product.image}",
            "brand": {"@type": "Brand", "name": STORE_NAME},
            "offers": {
                "@type": "Offer",
                "price": product.price_str,
                "priceCurrency": product.currency,
                "availability": "https://schema.org/" + ("OutOfStock" if listed_out else "InStock"),
                "url": str(request.url),
            },
        }
        if flaws["currency_missing"]:
            del json_ld["offers"]["priceCurrency"]
        return render(
            request,
            "product.html",
            product=product,
            next_product=next_product,
            related=related,
            buy_url=checkout_entry(request, product),
            json_ld=json.dumps(json_ld, indent=2).replace("</", "<\\/"),
            listed_out=listed_out,
            buyable=product.in_stock or flaws["oos_buyable"],
            was_price=catalog.sale_was_price(product),
            show_cookie_banner=flaws["cookie_banner"] and request.cookies.get(COOKIE_CONSENT) != "1",
            paypal_client_id=paypal_client_id,
            paypal_sdk_url=paypal_sdk_url,
        )

    @app.get("/checkout/details", response_class=HTMLResponse)
    def details_form(request: Request, sku: str):
        product = require_product(sku)
        if not flaw_store.get_all()["extra_checkout_step"]:
            return RedirectResponse(f"{request.scope.get('root_path', '')}/checkout?sku={sku}", status_code=303)
        return render(request, "details.html", product=product, referral_options=REFERRAL_OPTIONS, errors=[], form={})

    @app.post("/checkout/details", response_class=HTMLResponse)
    def details_submit(
        request: Request,
        sku: str = Form(...),
        email: str = Form(""),
        referral: str = Form(""),
        agree: str = Form(""),
    ):
        product = require_product(sku)
        errors = []
        if "@" not in email:
            errors.append("Please enter a valid email address.")
        if referral not in REFERRAL_OPTIONS:
            errors.append("Please tell us how you heard about us.")
        if agree != "yes":
            errors.append("You must agree to the store policies to continue.")
        if errors:
            return render(
                request,
                "details.html",
                product=product,
                referral_options=REFERRAL_OPTIONS,
                errors=errors,
                form={"email": email, "referral": referral},
            )
        base = request.scope.get("root_path", "")
        resp = RedirectResponse(f"{base}/checkout?sku={sku}", status_code=303)
        resp.set_cookie(DETAILS_COOKIE, sku, path=base or "/", httponly=True, samesite="lax")
        return resp

    @app.get("/checkout", response_class=HTMLResponse)
    def checkout(request: Request, sku: str):
        product = require_product(sku)
        base = request.scope.get("root_path", "")
        if flaw_store.get_all()["extra_checkout_step"] and request.cookies.get(DETAILS_COOKIE) != sku:
            return RedirectResponse(f"{base}/checkout/details?sku={sku}", status_code=303)
        flaws = flaw_store.get_all()
        return render(
            request,
            "checkout.html",
            product=product,
            unit_price=f"{catalog.charged_unit_price(product, flaws):.2f}",
            buyable=product.in_stock or flaws["oos_buyable"],
            paypal_client_id=paypal_client_id,
            paypal_sdk_url=paypal_sdk_url,
        )

    @app.post("/checkout/account", response_class=HTMLResponse)
    def create_account(request: Request, sku: str = Form(...), email: str = Form(""), password: str = Form("")):
        product = require_product(sku)
        flaws = flaw_store.get_all()
        notice = (
            "Please enter a valid email address and a password of at least 8 characters."
            if "@" not in email or len(password) < 8
            else "We sent a confirmation link to your email. Confirm your account, then sign in to pay."
        )
        return render(
            request,
            "checkout.html",
            product=product,
            unit_price=f"{catalog.charged_unit_price(product, flaws):.2f}",
            buyable=product.in_stock or flaws["oos_buyable"],
            paypal_client_id=paypal_client_id,
            paypal_sdk_url=paypal_sdk_url,
            account_notice=notice,
        )

    @app.get("/thanks", response_class=HTMLResponse)
    def thanks(request: Request, order: str = "", capture: str = "", store_order: int | None = None):
        placed = store_orders.get(store_order) if store_order is not None else None
        return render(request, "thanks.html", order_id=order, capture_id=capture, placed=placed,
                      status_label=STATUS_LABELS[placed["status"]] if placed else "")

    @app.get("/orders/{number}", response_class=HTMLResponse)
    def order_status(request: Request, number: int):
        placed = store_orders.get(number)
        if placed is None:
            raise HTTPException(status_code=404, detail="Order not found")
        return render(request, "order.html", placed=placed, product=catalog.get_by_sku(placed["sku"]),
                      status_label=STATUS_LABELS[placed["status"]])

    @app.get("/newsletter", response_class=HTMLResponse)
    def newsletter(request: Request):
        return render(request, "newsletter.html")

    @app.get("/credits", response_class=HTMLResponse)
    def credits(request: Request):
        return render(request, "credits.html")

    @app.get("/media/p/{token}.svg")
    def price_image(token: str):
        amount = price_tokens.get(token)
        if amount is None:
            raise HTTPException(status_code=404)
        return Response(render_price_svg(amount), media_type="image/svg+xml")

    # --- Flaw toggles (demo control panel, not part of the "merchant" UI) ---

    def admin_allowed(request: Request) -> bool:
        if admin_open:
            return True
        return token_matches(request.headers.get("x-admin-token") or "") or has_admin_cookie(request, admin_token)

    def token_matches(supplied: str) -> bool:
        return bool(admin_token) and hmac.compare_digest(supplied.encode(), admin_token.encode())

    def unlock_page(request: Request, wrong: bool = False) -> HTMLResponse:
        return render(request, "admin_unlock.html", wrong=wrong, status_code=403)

    def require_admin(request: Request) -> None:
        if not admin_allowed(request):
            raise HTTPException(status_code=403, detail="The demo store's settings are locked on this server.")

    @app.get("/admin", response_class=HTMLResponse)
    def admin(request: Request, saved: bool = False):
        if not admin_allowed(request):
            if not admin_token:
                require_admin(request)  # nothing can unlock it on this server: plain 403
            return unlock_page(request)
        return render(request, "admin.html", flaw_defs=FLAWS, classic=CLASSIC_FLAWS, saved=saved)

    @app.post("/admin/unlock")
    def admin_unlock(request: Request, token: str = Form("")):
        base = request.scope.get("root_path", "")
        if admin_open:
            return RedirectResponse(f"{base}/admin", status_code=303)
        if unlock_allowed is not None and not unlock_allowed(request):
            raise HTTPException(status_code=429, detail="Too many unlock attempts. Please wait a few minutes and try again.")
        if not token_matches(token):
            return unlock_page(request, wrong=True)
        resp = RedirectResponse(f"{base}/admin", status_code=303)
        resp.set_cookie(ADMIN_COOKIE, admin_cookie_value(admin_token), httponly=True, samesite="strict",
                        secure=request.url.scheme == "https", path="/", max_age=12 * 3600)
        return resp

    @app.post("/admin")
    async def admin_save(request: Request):
        require_admin(request)
        form = await request.form()
        flaw_store.set_many({f.key: form.get(f.key) == "on" for f in FLAWS})
        return RedirectResponse(f"{request.scope.get('root_path', '')}/admin?saved=1", status_code=303)

    @app.get("/admin/flaws.json")
    def get_flaws():
        return flaw_store.get_all()

    @app.put("/admin/flaws.json")
    def put_flaws(body: FlawUpdate, request: Request):
        require_admin(request)
        try:
            return flaw_store.set_many(body.flaws)
        except KeyError as exc:
            raise HTTPException(status_code=422, detail=f"Unknown flaw: {exc.args[0]}") from exc

    return app
