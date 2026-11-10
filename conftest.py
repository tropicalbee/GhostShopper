import os
import tempfile
from pathlib import Path

import pytest

# Tests must never reach paid live services because of a developer's .env. backend.app.config runs
# load_dotenv (override=False) on import, so values set here, before any app import, win over .env.
# An empty string counts as unset for every reader of these variables.
os.environ["BROWSER_PROVIDER"] = "local"
for _name in ("KERNEL_API_KEY", "CHANNEL3_API_KEY", "LLM_API_KEY", "GROQ_API_KEY"):
    os.environ[_name] = ""


@pytest.fixture
def tmp_path() -> Path:
    # pytest's own tmp_path base dir is not accessible in this environment, so use a fresh
    # system temp dir per test. Nothing is deleted automatically; the OS temp cleaner owns it.
    return Path(tempfile.mkdtemp(prefix="ghostshopper-test-"))


@pytest.fixture
def anyio_backend() -> str:
    # Async tests run via anyio's pytest plugin (ships with Starlette); asyncio only.
    return "asyncio"
