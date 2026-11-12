"""The key that makes the order read and verify routes agent-only.

The server makes a random key at startup and keeps it in memory. In-process runs read it from there; CLI runs, which
talk to a separately started server over HTTP, read it from a file next to the database. It is never logged, and
never given to the LLM, the recorder, run logs or the browser.
"""

import hmac
import os
import secrets
from pathlib import Path

from .config import get_settings

HEADER = "X-GhostShopper-Key"
KEY_FILE = ".internal_key"


def key_path(database_path: Path) -> Path:
    return Path(database_path).parent / KEY_FILE


def new_key() -> str:
    return secrets.token_urlsafe(32)


def write_key(database_path: Path, key: str) -> None:
    """Publish the key for CLI runs, atomically so they never read half of it. Overwritten at every server start."""
    path = key_path(database_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(key, encoding="utf-8")
    try:
        os.chmod(tmp, 0o600)
    except OSError:
        pass  # best effort: Windows ignores most mode bits
    os.replace(tmp, path)


def read_key_file(database_path: Path | None = None) -> str | None:
    """The running server's key, for a run in another process. None when no server has written one."""
    path = key_path(database_path or get_settings().database_path)
    try:
        return path.read_text(encoding="utf-8").strip() or None
    except OSError:
        return None


def key_header(key: str | None) -> dict[str, str]:
    return {HEADER: key} if key else {}


def key_ok(expected: str | None, given: str | None) -> bool:
    return bool(expected) and bool(given) and hmac.compare_digest(expected.encode(), given.encode())
