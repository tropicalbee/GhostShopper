import tempfile
from pathlib import Path

import pytest


@pytest.fixture
def tmp_path() -> Path:
    # pytest's own tmp_path base dir is not accessible in this environment, so use a fresh
    # system temp dir per test. Nothing is deleted automatically; the OS temp cleaner owns it.
    return Path(tempfile.mkdtemp(prefix="ghostshopper-test-"))


@pytest.fixture
def anyio_backend() -> str:
    # Async tests run via anyio's pytest plugin (ships with Starlette); asyncio only.
    return "asyncio"
