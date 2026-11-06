"""The demo store's product catalog. The backend prices orders from here, never from the browser."""

import json
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from functools import lru_cache
from pathlib import Path

PRODUCTS_FILE = Path(__file__).with_name("products.json")
PRICE_MISMATCH_SURCHARGE = Decimal("3.00")  # flaw price_mismatch: added per item at checkout
SALE_WAS_FACTOR = Decimal("1.25")  # flaw misleading_sale: fake "was" price (a 20% discount, claimed as 50%)
CATEGORIES = {"mugs-cups": "Mugs & cups", "coffee-tea": "Coffee & tea", "bowls-plates": "Bowls & plates", "vases": "Vases"}


def charged_unit_price(product: "Product", flaws: dict[str, bool]) -> Decimal:
    """What checkout shows and the backend charges per item. Equal to the advertised price unless the
    price_mismatch flaw is on."""
    return product.price + (PRICE_MISMATCH_SURCHARGE if flaws.get("price_mismatch") else 0)


def sale_was_price(product: "Product") -> str:
    return f"{(product.price * SALE_WAS_FACTOR).quantize(Decimal('0.01')):.2f}"


@dataclass(frozen=True)
class Review:
    """Sample customer review shown on the demo store. Fictional, like the store itself."""

    author: str
    location: str
    rating: int
    date: str
    title: str
    body: str

    @property
    def display_date(self) -> str:
        d = date.fromisoformat(self.date)
        return f"{d:%B} {d.day}, {d.year}"


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
    category: str = ""
    reviews: tuple[Review, ...] = ()

    @property
    def price_str(self) -> str:
        return f"{self.price:.2f}"

    @property
    def category_name(self) -> str:
        return CATEGORIES.get(self.category, "")

    @property
    def rating(self) -> Decimal | None:
        """Average review rating to one decimal, or None without reviews."""
        if not self.reviews:
            return None
        return (Decimal(sum(r.rating for r in self.reviews)) / len(self.reviews)).quantize(Decimal("0.1"))


@lru_cache(maxsize=1)
def load_products() -> tuple[Product, ...]:
    raw = json.loads(PRODUCTS_FILE.read_text(encoding="utf-8"))
    return tuple(
        Product(**{**item, "price": Decimal(item["price"]), "details": tuple(item["details"]),
                   "reviews": tuple(Review(**r) for r in item.get("reviews", ()))})
        for item in raw
    )


def get_by_sku(sku: str) -> Product | None:
    return next((p for p in load_products() if p.sku == sku), None)


def get_by_slug(slug: str) -> Product | None:
    return next((p for p in load_products() if p.slug == slug), None)
