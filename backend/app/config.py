"""Settings loaded from the environment (and .env at the repo root)."""

import os
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[2]

load_dotenv(REPO_ROOT / ".env")

# Sandbox only, by design. There is deliberately no switch to the live API.
PAYPAL_API_BASE = "https://api-m.sandbox.paypal.com"
PAYPAL_SDK_URL = "https://www.sandbox.paypal.com/web-sdk/v6/core"


PAYPAL_MODES = ("sandbox", "mock")


@dataclass(frozen=True)
class Settings:
    paypal_client_id: str
    paypal_client_secret: str
    database_path: Path
    app_base_url: str
    # sandbox: real PayPal sandbox. mock: fake Orders client + mock SDK/popup, no PayPal calls at all.
    paypal_mode: str = "sandbox"
    # Developer options on POST /api/runs (llm, cassette, record, flaws, checkout, browser, max_steps, paypal)
    # and an unlocked demo store settings page. Off unless the server runs on localhost or DEV_OPTIONS=1.
    dev_options: bool = False
    # Unlocks /store/admin on a deployed server for the presenter (typed once into its unlock form, then a cookie).
    demo_admin_token: str = ""
    runs_dir: Path = REPO_ROOT / "runs"  # screenshots, one folder per run
    frontend_dist: Path = REPO_ROOT / "frontend" / "dist"
    retention_days: int = 30  # owned checks older than this are deleted at startup; examples are kept
    example_runs: bool = False  # load the bundled example checks (backend/app/examples/) at startup if missing
    run_rate_limit: tuple[int, int] = (6, 600)  # starts per (client IP, browser) per window in seconds
    api_rate_limit: tuple[int, int] = (30, 600)  # explain, market and PayPal order calls, which cost quota
    unlock_rate_limit: tuple[int, int] = (10, 900)  # admin unlock attempts per client IP per window in seconds
    # Process-wide caps per day (all callers together) on the calls that spend real quota; the admin cookie skips them.
    run_daily_cap: int = 40
    market_daily_cap: int = 100
    order_daily_cap: int = 100
    catalog_daily_cap: int = 100
    vault_token_id: str = ""  # a saved sandbox buyer for hosted real-sandbox runs; seeded into the database at startup
    vault_customer_id: str = ""
    # How many proxies in front of us append to X-Forwarded-For (Render: 1). The client IP is that many entries from the right.
    trusted_proxy_hops: int = 1

    @property
    def paypal_configured(self) -> bool:
        return bool(self.paypal_client_id and self.paypal_client_secret)

    @property
    def https(self) -> bool:
        return self.app_base_url.startswith("https://")


LOCAL_HOSTS = ("localhost", "127.0.0.1", "::1")


def _flag(name: str) -> bool | None:
    value = os.getenv(name, "").strip().lower()
    if value in ("1", "true", "yes"):
        return True
    if value in ("0", "false", "no"):
        return False
    if value:
        raise ValueError(f"{name} must be 1 or 0, got {value!r}")
    return None


def _count(name: str, default: int, minimum: int = 1) -> int:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    if not raw.isdigit() or int(raw) < minimum:
        raise ValueError(f"{name} must be a whole number of {minimum} or more, got {raw!r}")
    return int(raw)


def get_settings() -> Settings:
    db_path = Path(os.getenv("DATABASE_PATH", "data/ghostshopper.db"))
    if not db_path.is_absolute():
        db_path = REPO_ROOT / db_path
    mode = os.getenv("PAYPAL_MODE", "sandbox").strip().lower() or "sandbox"
    if mode not in PAYPAL_MODES:
        raise ValueError(f"PAYPAL_MODE must be one of {PAYPAL_MODES}, got {mode!r}")
    base = os.getenv("APP_BASE_URL", "http://localhost:8000").rstrip("/")
    dev = _flag("DEV_OPTIONS")
    retention = os.getenv("RETENTION_DAYS", "30").strip()
    if not retention.isdigit() or int(retention) < 1:
        raise ValueError(f"RETENTION_DAYS must be a whole number of days (1 or more), got {retention!r}")
    caps = {name: _count(name, default) for name, default in (("RUN_DAILY_CAP", 40), ("MARKET_DAILY_CAP", 100), ("ORDER_DAILY_CAP", 100), ("CATALOG_DAILY_CAP", 100))}
    return Settings(
        paypal_client_id=os.getenv("PAYPAL_CLIENT_ID", "").strip(),
        paypal_client_secret=os.getenv("PAYPAL_CLIENT_SECRET", "").strip(),
        database_path=db_path,
        app_base_url=base,
        paypal_mode=mode,
        dev_options=dev if dev is not None else (urlparse(base).hostname or "") in LOCAL_HOSTS,
        demo_admin_token=os.getenv("DEMO_ADMIN_TOKEN", "").strip(),
        retention_days=int(retention),
        example_runs=bool(_flag("EXAMPLE_RUNS")),
        run_daily_cap=caps["RUN_DAILY_CAP"],
        market_daily_cap=caps["MARKET_DAILY_CAP"],
        order_daily_cap=caps["ORDER_DAILY_CAP"],
        catalog_daily_cap=caps["CATALOG_DAILY_CAP"],
        vault_token_id=os.getenv("PAYPAL_VAULT_TOKEN_ID", "").strip(),
        vault_customer_id=os.getenv("PAYPAL_VAULT_CUSTOMER_ID", "").strip(),
        trusted_proxy_hops=_count("TRUSTED_PROXY_HOPS", 1, minimum=0),
    )


def vision_model() -> str:
    """VISION_MODEL: the model id the shopper uses to look at pages ('' when not set). It runs on the same
    provider, base URL and key as the main LLM (LLM_PROVIDER, LLM_API_KEY, LLM_BASE_URL)."""
    return os.getenv("VISION_MODEL", "").strip()


@dataclass(frozen=True)
class BuyerCredentials:
    """Sandbox buyer login. repr is masked so it can never leak into logs or tracebacks."""

    email: str
    password: str

    def __repr__(self) -> str:
        return "BuyerCredentials(***)"

    __str__ = __repr__


def sandbox_buyer() -> BuyerCredentials | None:
    """Read only from SANDBOX_BUYER_EMAIL / SANDBOX_BUYER_PASSWORD. None if either is missing."""
    email = os.getenv("SANDBOX_BUYER_EMAIL", "").strip()
    password = os.getenv("SANDBOX_BUYER_PASSWORD", "")
    if not email or not password:
        return None
    return BuyerCredentials(email, password)
