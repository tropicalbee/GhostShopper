"""LLM backends for the shopper agent: live Groq, or replay of recorded responses (cassettes).

All backends speak the OpenAI chat-completions message format, which Groq implements.
"""

import asyncio
import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

import httpx

from .. import config  # noqa: F401  (loads .env)

GROQ_BASE_URL = "https://api.groq.com/openai/v1"
CASSETTE_DIR = Path(__file__).with_name("cassettes")


class LLMConfigError(RuntimeError):
    pass


class CassetteExhausted(RuntimeError):
    pass


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any]


@dataclass
class LLMReply:
    content: str | None
    tool_calls: list[ToolCall]
    message: dict[str, Any] = field(repr=False)  # assistant message to append to the history


class LLM(Protocol):
    kind: str
    model: str | None

    async def complete(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> LLMReply: ...


def parse_message(message: dict[str, Any]) -> LLMReply:
    calls = []
    for tc in message.get("tool_calls") or []:
        raw = tc["function"].get("arguments") or "{}"
        try:
            args = json.loads(raw) if isinstance(raw, str) else raw
        except json.JSONDecodeError:
            args = {"_invalid_json": raw}
        calls.append(ToolCall(tc["id"], tc["function"]["name"], args if isinstance(args, dict) else {}))
    clean = {"role": "assistant", "content": message.get("content")}
    if message.get("tool_calls"):
        clean["tool_calls"] = message["tool_calls"]
    return LLMReply(message.get("content"), calls, clean)


class GroqLLM:
    kind = "groq"

    def __init__(self, api_key: str, model: str, http: httpx.AsyncClient | None = None, max_retries: int = 3):
        self.model = model
        self._http = http or httpx.AsyncClient(
            base_url=GROQ_BASE_URL, timeout=60.0, headers={"Authorization": f"Bearer {api_key}"}
        )
        self._max_retries = max_retries

    async def complete(self, messages, tools) -> LLMReply:
        payload: dict[str, Any] = {"model": self.model, "messages": messages, "temperature": 0}
        if tools:  # text-only calls (fix rephrasing, judge) send no tools and no tool_choice
            payload |= {"tools": tools, "tool_choice": "auto"}
        for attempt in range(self._max_retries + 1):
            resp = await self._http.post("/chat/completions", json=payload)
            # Free tier: back off on rate limits and transient errors.
            if resp.status_code in (429, 500, 502, 503) and attempt < self._max_retries:
                wait = min(float(resp.headers.get("retry-after", 2 ** attempt)), 20.0)
                await asyncio.sleep(wait)
                continue
            if resp.status_code != 200:
                raise RuntimeError(f"Groq API error {resp.status_code}: {resp.text[:300]}")
            return parse_message(resp.json()["choices"][0]["message"])
        raise RuntimeError("Groq API: retries exhausted")

    async def aclose(self) -> None:
        await self._http.aclose()


class ReplayLLM:
    """Plays back recorded assistant messages in order. Fails loudly when they run out."""

    kind = "mock"

    def __init__(self, cassette: Path):
        data = json.loads(cassette.read_text(encoding="utf-8"))
        self.model = f"replay:{cassette.stem} (recorded from {data.get('recorded_from', 'hand-written')})"
        self._responses: list[dict[str, Any]] = data["responses"]
        self._i = 0

    async def complete(self, messages, tools) -> LLMReply:
        if self._i >= len(self._responses):
            raise CassetteExhausted(f"Cassette has only {len(self._responses)} responses")
        message = self._responses[self._i]
        self._i += 1
        names = {t["function"]["name"] for t in tools}
        for tc in message.get("tool_calls") or []:
            if tc["function"]["name"] not in names:
                raise CassetteExhausted(f"Recorded tool {tc['function']['name']!r} is not offered in this run")
        return parse_message(message)


class RecordingLLM:
    """Wraps a live LLM and saves every reply as a cassette, so a live run can be replayed in tests."""

    def __init__(self, inner: LLM, path: Path):
        self._inner = inner
        self._path = path
        self._responses: list[dict[str, Any]] = []
        self.kind = inner.kind
        self.model = inner.model

    async def complete(self, messages, tools) -> LLMReply:
        reply = await self._inner.complete(messages, tools)
        self._responses.append(reply.message)
        # Rewrite the whole file each turn so a crashed run still leaves a usable cassette.
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(
            json.dumps({"recorded_from": f"{self.kind}:{self.model}", "responses": self._responses}, indent=2),
            encoding="utf-8",
        )
        return reply

    async def aclose(self) -> None:
        close = getattr(self._inner, "aclose", None)
        if close:
            await close()


def resolve_cassette(name: str) -> Path:
    """Cassettes are referenced by name only (no paths), e.g. 'day2_flaws_on'."""
    if not name.replace("_", "").replace("-", "").isalnum():
        raise LLMConfigError(f"Invalid cassette name {name!r}")
    path = CASSETTE_DIR / f"{name}.json"
    if not path.is_file():
        available = ", ".join(sorted(p.stem for p in CASSETTE_DIR.glob("*.json")))
        raise LLMConfigError(f"No cassette {name!r}. Available: {available}")
    return path


def make_llm(kind: str, cassette: str | None = None, record_to: Path | None = None) -> LLM:
    """kind is 'groq' (live, needs GROQ_API_KEY + GROQ_MODEL) or 'mock' (replay a cassette)."""
    if kind == "mock":
        if not cassette:
            raise LLMConfigError("Mock LLM needs a cassette name")
        return ReplayLLM(resolve_cassette(cassette))
    if kind == "groq":
        key = os.getenv("GROQ_API_KEY", "").strip()
        model = os.getenv("GROQ_MODEL", "").strip()
        if not key or not model:
            raise LLMConfigError("Live LLM needs GROQ_API_KEY and GROQ_MODEL in .env (or use --llm mock)")
        llm: LLM = GroqLLM(key, model)
        return RecordingLLM(llm, record_to) if record_to else llm
    raise LLMConfigError(f"Unknown LLM kind {kind!r}; use 'groq' or 'mock'")


def groq_configured() -> bool:
    return bool(os.getenv("GROQ_API_KEY", "").strip() and os.getenv("GROQ_MODEL", "").strip())
