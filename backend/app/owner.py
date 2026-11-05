"""Which browser a check belongs to, without accounts.

Each browser gets a random token in an httpOnly cookie. The database keeps only its SHA-256 hash, so a
leaked database can't be used to impersonate a browser. Runs with no owner (made by the CLI or the seed
command) are the shared examples everyone can read.
"""

import hashlib
import re
import secrets

COOKIE = "gs_owner"
MAX_AGE_S = 180 * 24 * 3600
_TOKEN_RE = re.compile(r"[A-Za-z0-9_-]{43}")


def new_token() -> str:
    return secrets.token_urlsafe(32)  # 256 bits, 43 characters


def valid_token(token: str | None) -> bool:
    return bool(token) and _TOKEN_RE.fullmatch(token) is not None


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()
