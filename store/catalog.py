"""The demo store's product catalog. The backend prices orders from here, never from the browser."""

import json
from dataclasses import dataclass
from decimal import Decimal
from functools import lru_cache
from pathlib import Path

PRODUCTS_FILE = Path(__file__).with_name("products.json")
PRICE_MISMATCH_SURCHARGE = Decimal("3.00")  # flaw price_mismatch: added per item at checkout
SALE_WAS_FACTOR = Decimal("1.25")  # flaw misleading_sale: fake "was" price (a 20% discount, claimed as 50%)


def charged_unit_price(product: "Product", flaws: dict[str, bool]) -> Decimal:
    """What checkout shows and the backend charges per item. Equal to the advertised price unless the
    price_mismatch flaw is on."""
    return product.price + (PRICE_MISMATCH_SURCHARGE if flaws.get("price_mismatch") else 0)


def sale_was_price(product: "Product") -> str:
    return f"{(product.price * SALE_WAS_FACTOR).quantize(Decimal('0.01')):.2f}"


@dataclass(frozen=True)
class Product:
    sku: str
    slug: str
    name: str
    price: Decimal
    currency: str
    in_stock: bool
    image: str
    summary: str
    description: str
    details: tuple[str, ...]

    @property
    def price_str(self) -> str:
        return f"{self.price:.2f}"


@lru_cache(maxsize=1)
def load_products() -> tuple[Product, ...]:
    raw = json.loads(PRODUCTS_FILE.read_text(encoding="utf-8"))
    return tuple(
        Product(**{**item, "price": Decimal(item["price"]), "details": tuple(item["details"])}) for item in raw
    )


def get_by_sku(sku: str) -> Product | None:
    return next((p for p in load_products() if p.sku == sku), None)


def get_by_slug(slug: str) -> Product | None:
    return next((p for p in load_products() if p.slug == slug), None)
