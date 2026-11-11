import os

from backend.app.agent.browser import resolve_provider


def test_dotenv_cannot_enable_paid_services_in_tests():
    assert resolve_provider(None) == "local"
    for name in ("KERNEL_API_KEY", "CHANNEL3_API_KEY", "LLM_API_KEY"):
        assert not os.getenv(name, "").strip()
