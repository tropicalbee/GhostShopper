"""A rule-based shopper for the WebMCP tools (--llm scripted): search, read, check out, complete, finish. Not an LLM:
it only reads each tool result and picks the next of the four shopping tools. For tests and offline demos."""

import json
import re
import uuid
from typing import Any

from ..agent.llm import ChatModel, LLMReply, ToolCall, parse_message

_RESULT = re.compile(r"<tool_result>\n(.*)\n</tool_result>", re.S)


class ScriptedWebMCP(ChatModel):
    kind = "scripted"
    model = "webmcp-rules"

    def __init__(self, target: str):
        self.target = target

    @staticmethod
    def _function(tools: list[dict[str, Any]], suffix: str) -> str:
        return next(t["function"]["name"] for t in tools if t["function"]["name"].endswith(suffix))

    @staticmethod
    def _results(messages: list[dict[str, Any]]) -> list[str]:
        out = []
        for m in messages:
            if m.get("role") == "tool":
                found = _RESULT.search(m.get("content") or "")
                out.append(found.group(1) if found else m.get("content") or "")
        return out

    def _reply(self, name: str, arguments: dict[str, Any]) -> LLMReply:
        return parse_message({"role": "assistant", "content": None, "tool_calls": [{
            "id": f"call_{uuid.uuid4().hex[:8]}", "type": "function",
            "function": {"name": name, "arguments": json.dumps(arguments)}}]})

    def _finish(self, outcome: str, summary: str, price: str = "unknown", order: str = "none") -> LLMReply:
        return self._reply("finish", {"outcome": outcome, "summary": summary, "price": price, "order": order})

    async def complete(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> LLMReply:
        results = self._results(messages)
        step = len(results)
        if step == 0:
            return self._reply(self._function(tools, "searchProducts"), {"query": self.target})
        last = results[-1]
        if step == 1:
            try:
                products = json.loads(last).get("products") or []
            except ValueError:
                products = []
            wanted = next((p for p in products if self.target.lower() in str(p.get("title", "")).lower()), None)
            if wanted is None:
                return self._finish("gave_up", f"No product matching '{self.target}' in the search results.")
            return self._reply(self._function(tools, "getProduct"), {"product_id": wanted["product_id"]})
        if step == 2:
            product = json.loads(last)
            return self._reply(self._function(tools, "initiateCheckout"), {
                "product_id": product["product_id"], "quantity": 1, "requires_user_approval": True})
        if step == 3:
            if "Buyer approval: approved" in last:
                return self._reply(self._function(tools, "completeCheckout"), {})
            return self._finish("blocked", "The buyer's PayPal approval did not complete, so nothing was paid.")
        try:
            done = json.loads(last.split("\n")[0])
        except ValueError:
            done = {}
        if done.get("capture_id"):
            price = (done.get("amount") or {}).get("value", "unknown")
            return self._finish("purchased", f"Bought one {self.target}.", price, str(done.get("store_order_number") or done.get("order_id")))
        return self._finish("blocked", f"Checkout did not complete: {last[:200]}")
