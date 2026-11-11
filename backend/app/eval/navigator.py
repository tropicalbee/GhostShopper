"""A scripted, rule-based navigator behind the LLM interface, for detection benchmarks.

It is NOT an LLM and is labelled as such in every run it makes (llm="scripted"). It exists because the
benchmark runs many random flaw combinations: replayed cassettes can't adapt to a store that changes,
and a free-tier LLM can't afford that many runs. It measures the deterministic detectors (which only
need the agent to visit the pages); agent behaviour itself is measured with live LLM runs.

Strategy, like a cautious shopper: open the product from the home page, accept a cookie banner if one
is in the way, try buy-like controls in order (semantic buy buttons first, then unlabeled clickables),
go back after a wrong turn, fill any form that stands between it and checkout, then pay or finish.
"""

import json
import re
from typing import Any

from ..agent.checks import BUY_RE
from ..agent.llm import ChatModel, LLMReply, ToolCall

LINE_RE = re.compile(r"^(e\d+) (.+?) '(.*?)'(.*)$")
WHERE_RE = re.compile(r"Now on: (.*) \((https?://[^)\s]+)\)")
COOKIE_RE = re.compile(r"^(accept|accept all|allow all|ok|got it|i agree)$", re.I)
NAV_TEXT = {"shop", "newsletter", "back to shop", "fernhill ceramics", "continue shopping"}
PRODUCT_HREF_RE = re.compile(r"/(products?|product-page|item|items|p|shop)/[^/?#]+", re.I)
CHECKOUT_RE = re.compile(r"(check ?out|proceed to checkout|go to checkout|view cart|cart)", re.I)


def parse_elements(observation: str) -> list[dict[str, Any]]:
    """Parse find_elements output lines like: e5 button 'Buy now' -> /x (required)."""
    out = []
    for line in observation.splitlines():
        m = LINE_RE.match(line.strip())
        if not m:
            continue
        eid, kind, text, rest = m.groups()
        el = {"id": eid, "kind": kind, "text": text, "semantic": "not a real button" not in kind}
        if " -> " in rest:
            el["href"] = rest.split(" -> ", 1)[1].split(" ")[0]
        if " options: " in rest:
            el["options"] = [o.strip() for o in rest.split(" options: ", 1)[1].replace(" (required)", "").split(" | ")]
        out.append(el)
    return out


class ScriptedNavigator(ChatModel):
    kind = "scripted"
    model = "scripted-navigator-v1 (rule-based, not an LLM)"

    def __init__(self, target: str | None, max_decisions: int = 45):
        self.target = (target or "").lower()  # empty on live stores: any product will do
        self._expect_product = False
        self._clicked_buy = False
        self.max_decisions = max_decisions
        self._n = 0
        self._state = "start"
        self._offered: set[str] = set()
        self._product_url: str | None = None
        self._product_read = False
        self._tried: set[str] = set()
        self._cookie_done = False
        self._form_checked: set[str] = set()  # pages already checked for a form
        self._form_url: str | None = None

    # -- helpers -----------------------------------------------------------------------------------

    def _call(self, thought: str, next_state: str, name: str, **args: Any) -> LLMReply:
        self._n += 1
        self._state = next_state
        call_id = f"nav_{self._n:02d}"
        message = {"role": "assistant", "content": thought, "tool_calls": [
            {"id": call_id, "type": "function", "function": {"name": name, "arguments": json.dumps(args)}}]}
        return LLMReply(thought, [ToolCall(call_id, name, args)], message)

    def _finish(self, outcome: str, summary: str) -> LLMReply:
        return self._call(summary, "done", "finish", outcome=outcome, summary=summary,
                          price="unknown", in_stock="unknown")

    def _back_to_product(self, why: str) -> LLMReply:
        if not self._product_url:
            return self._finish("gave_up", "Lost before finding the product.")
        return self._call(why, "landed", "open_page", url=self._product_url)

    # -- the policy --------------------------------------------------------------------------------

    async def complete(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> LLMReply:
        self._offered = {t["function"]["name"] for t in tools}
        if self._n >= self.max_decisions:
            return self._finish("gave_up", "Scripted navigator ran out of decisions.")
        last = next((m["content"] for m in reversed(messages) if m.get("role") == "tool"), "") or ""
        s = self._state
        if s == "start":
            return self._call("Open the store.", "pick_product_list", "open_page",
                              url="/store/" if self.target else "/")
        if s == "pick_product_list":
            return self._call("List the links.", "pick_product", "find_elements", kind="links")
        if s == "pick_product":
            els = parse_elements(last)
            if self.target:
                link = next((e for e in els if e["kind"] == "a" and self.target in e["text"].lower()), None)
            else:
                link = next((e for e in els if e["kind"] == "a" and e["text"]
                             and PRODUCT_HREF_RE.search(e.get("href") or "")), None)
            if not link:
                return self._finish("gave_up", "No product is linked from the home page.")
            self._expect_product = not self.target
            return self._call(f"Open '{link['text']}'.", "landed", "click", element_id=link["id"])
        if s == "live_cart":
            els = parse_elements(last)
            if any("paypal" in (e["text"] + e["kind"]).lower() for e in els):
                return self._call("Check the PayPal button, without clicking it.", "checked", "check_paypal_button")
            go = next((e for e in els if e["semantic"] and CHECKOUT_RE.search(e["text"])
                       and e["text"] not in self._tried), None)
            if go:
                self._tried.add(go["text"])
                return self._call(f"Go on with '{go['text']}'.", "landed", "click", element_id=go["id"])
            return self._call("Check the PayPal button.", "checked", "check_paypal_button")
        if s == "checked":
            return self._finish("reached_checkout", last[:200])
        if s == "landed":
            return self._route(last)
        if s == "list_controls":
            return self._call("List the controls.", "choose", "find_elements")
        if s == "choose":
            return self._choose(last)
        if s == "form_or_back":
            return self._form_or_back(last)
        if s == "submit_list":
            return self._call("Find the submit button.", "submit", "find_elements", kind="buttons")
        if s == "submit":
            btn = next((e for e in parse_elements(last)
                        if e["semantic"] and e["text"].lower() not in NAV_TEXT and "paypal" not in e["kind"]), None)
            if not btn:
                return self._back_to_product("No submit button; back to the product.")
            return self._call(f"Submit with '{btn['text']}'.", "landed", "click", element_id=btn["id"])
        if s == "pay":
            return self._call("Pay with PayPal.", "paid", "pay_with_paypal")
        if s == "paid":
            return self._finish("purchased" if last.startswith("Payment complete") else "blocked", last[:200])
        return self._finish("gave_up", f"Unexpected state {s!r}.")

    def _route(self, last: str) -> LLMReply:
        """Decide what the page we just landed on is."""
        if last.startswith("Error"):
            return self._call("That did not work; look again.", "choose", "find_elements")
        where = WHERE_RE.search(last)
        title, url = (where.group(1).lower(), where.group(2)) if where else ("", "")
        on_product = (self.target in title) if self.target else (self._expect_product or url == self._product_url)
        self._expect_product = False
        if on_product and self._clicked_buy and "check_paypal_button" in self._offered:
            # Added to cart without leaving the page (common on live stores): go to the cart.
            self._clicked_buy = False
            return self._call("Added to cart; open the cart.", "landed", "open_page", url="/cart")
        if on_product:
            self._product_url = url
            if not self._product_read:
                self._product_read = True
                return self._call("Read the product page.", "list_controls", "read_text")
            return self._call("List the controls.", "choose", "find_elements")
        if "check_paypal_button" in self._offered:  # live store: cart or checkout, never pay
            return self._call("Look for checkout and the PayPal button.", "live_cart", "find_elements")
        if title.startswith("checkout"):
            if "pay_with_paypal" in self._offered:
                return self._call("Check the checkout page.", "pay", "read_text")
            return self._finish("reached_checkout", "Reached checkout.")
        if url and url not in self._form_checked:
            self._form_checked.add(url)
            self._form_url = url
            return self._call("Is there a form here?", "form_or_back", "find_elements", kind="inputs")
        return self._back_to_product("Wrong page; back to the product.")

    def _choose(self, last: str) -> LLMReply:
        els = parse_elements(last)
        if not self._cookie_done:
            cookie = next((e for e in els if COOKIE_RE.match(e["text"].strip())), None)
            if cookie:
                self._cookie_done = True
                return self._call("Accept the cookie banner first.", "list_controls", "click", element_id=cookie["id"])
        semantic_buy = [e for e in els if e["semantic"] and BUY_RE.search(e["text"]) and "paypal" not in e["kind"]]
        clickables = [e for e in els if not e["semantic"]]
        for e in semantic_buy + clickables:
            if e["text"] not in self._tried:
                self._tried.add(e["text"])
                self._clicked_buy = e in semantic_buy
                return self._call(f"Try '{e['text']}'.", "landed", "click", element_id=e["id"])
        return self._finish("gave_up", "Tried every buy-like control without reaching checkout.")

    def _form_or_back(self, last: str) -> LLMReply:
        inputs = [e for e in parse_elements(last)
                  if e["kind"].startswith(("input", "select", "textarea"))
                  and e["kind"] not in ("input[submit]", "input[button]")]
        if not inputs:
            return self._back_to_product("Not a form; back to the product.")
        fields = []
        for e in inputs:
            if e["kind"] == "select":
                opts = [o for o in e.get("options", []) if o and not o.startswith("--")]
                fields.append({"element_id": e["id"], "value": opts[0] if opts else ""})
            elif e["kind"] in ("input[checkbox]", "input[radio]"):
                fields.append({"element_id": e["id"], "value": "true"})
            elif e["kind"] == "input[email]":
                fields.append({"element_id": e["id"], "value": "shopper@example.com"})
            else:
                fields.append({"element_id": e["id"], "value": "Test Shopper"})
        return self._call("Fill the form.", "submit_list", "fill_form", fields=fields)
