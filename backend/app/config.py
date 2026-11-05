"""Settings loaded from the environment (and .env at the repo root)."""

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[2]

load_dotenv(REPO_ROOT / ".env")

# Sandbox only, by design. There is deliberately no switch to the live API.
PAYPAL_API_BASE = "https://api-m.sandbox.paypal.com"
PAYPAL_SDK_URL = "https://www.sandbox.paypal.com/web-sdk/v6/core"


@dataclass(frozen=True)
class Settings:
    paypal_client_id: str
    paypal_client_secret: str
    database_path: Path
    app_base_url: str

    @property
    def paypal_configured(self) -> bool:
        return bool(self.paypal_client_id and self.paypal_client_secret)


def get_settings() -> Settings:
    db_path = Path(os.getenv("DATABASE_PATH", "data/ghostshopper.db"))
    if not db_path.is_absolute():
        db_path = REPO_ROOT / db_path
    return Settings(
        paypal_client_id=os.getenv("PAYPAL_CLIENT_ID", "").strip(),
        paypal_client_secret=os.getenv("PAYPAL_CLIENT_SECRET", "").strip(),
        database_path=db_path,
        app_base_url=os.getenv("APP_BASE_URL", "http://localhost:8000").rstrip("/"),
    )
