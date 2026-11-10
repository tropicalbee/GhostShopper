"""The LLM can never type into a password field, on demo or live stores."""

import pytest

from backend.app.agent.browser import ToolError
from backend.app.agent.loop import _dispatch

pytestmark = pytest.mark.anyio


class FakeTools:
    def __init__(self, has_password: bool):
        self.has_password = has_password
        self.filled = []

    async def has_password_field(self, fields):
        return self.has_password

    async def has_card_field(self, fields):
        return False

    async def fill_form(self, fields):
        self.filled.append(fields)
        return "Filled."


class FakeEngine:
    live = False


FIELDS = [{"element_id": "e1", "value": "hunter2"}]


async def test_password_field_is_refused_on_a_demo_store():
    tools = FakeTools(has_password=True)
    with pytest.raises(ToolError, match="password"):
        await _dispatch("fill_form", {"fields": FIELDS}, tools, None, FakeEngine(), None)
    assert tools.filled == []


async def test_ordinary_fields_are_filled():
    tools = FakeTools(has_password=False)
    out = await _dispatch("fill_form", {"fields": FIELDS}, tools, None, FakeEngine(), None)
    assert out == "Filled."
    assert tools.filled == [FIELDS]
