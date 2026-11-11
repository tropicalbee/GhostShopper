"""LLM backends for the shopper agent: a live provider (any OpenAI-compatible API, or Anthropic), or replay of
recorded responses (cassettes).

The OpenAI chat-completions message and tool format is the canonical internal format. Adapters translate
to and from it, so nothing outside this module depends on a provider. To add a provider, add one entry to
PROVIDERS (or one adapter class if its wire format is new).
"""

from __future__ import annotations

import abc
import asyncio
import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx

from .. import config  # noqa: F401  (loads .env)

GROQ_BASE_URL = "https://api.groq.com/openai/v1"
NVIDIA_BASE_URL = "https://integrate.api.nvidia.com/v1"
ANTHROPIC_BASE_URL = "https://api.anthropic.com/v1"
ANTHROPIC_VERSION = "2023-06-01"
MAX_BACKOFF_S = 20.0
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


class ChatModel(abc.ABC):
    """One chat model behind the agent. Subclasses translate to and from the OpenAI chat-completions format."""

    kind: str  # "mock", "scripted", or the provider name for live adapters
    model: str | None

    @abc.abstractmethod
    async def complete(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> LLMReply: ...

    async def aclose(self) -> None:
        return None

    async def __aenter__(self) -> ChatModel:
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        await self.aclose()


LLM = ChatModel  # kept so existing type hints and imports keep working


async def close_llm(llm: object) -> None:
    close = getattr(llm, "aclose", None)
    if close:
        await close()


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


async def _post_with_retry(
    http: httpx.AsyncClient, path: str, payload: dict[str, Any], provider: str,
    retry_statuses: tuple[int, ...], max_retries: int,
) -> dict[str, Any]:
    """POST JSON, backing off on rate limits, transient errors, timeouts and dropped connections.
    Errors name the provider, never the key."""
    for attempt in range(max_retries + 1):
        try:
            resp = await http.post(path, json=payload)
        except httpx.TransportError as exc:  # ReadTimeout, ConnectError, ...: a hosted model can stall on one request
            if attempt < max_retries:
                await asyncio.sleep(min(2 ** attempt, MAX_BACKOFF_S))
                continue
            raise RuntimeError(f"{provider} API: {type(exc).__name__} after {max_retries + 1} attempts") from exc
        if resp.status_code in retry_statuses and attempt < max_retries:
            try:
                wait = float(resp.headers.get("retry-after", 2 ** attempt))
            except ValueError:
                wait = float(2 ** attempt)
            await asyncio.sleep(min(wait, MAX_BACKOFF_S))
            continue
        if resp.status_code != 200:
            raise RuntimeError(f"{provider} API error {resp.status_code}: {resp.text[:300]}")
        return resp.json()
    raise RuntimeError(f"{provider} API: retries exhausted")


class OpenAICompatibleChat(ChatModel):
    """Any server that speaks OpenAI chat-completions: Groq, OpenAI, OpenRouter, Together, Ollama, vLLM, ..."""

    retry_statuses = (429, 500, 502, 503)

    def __init__(self, base_url: str, api_key: str | None, model: str, http: httpx.AsyncClient | None = None,
                 max_retries: int = 3, timeout: float = 60.0, provider: str = "openai-compatible"):
        self.kind = provider
        self.model = model
        self._provider = provider
        self._max_retries = max_retries
        headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        self._http = http or httpx.AsyncClient(base_url=base_url.rstrip("/"), timeout=timeout, headers=headers)

    async def complete(self, messages, tools) -> LLMReply:
        payload: dict[str, Any] = {"model": self.model, "messages": messages, "temperature": 0}
        if tools:  # text-only calls (fix rephrasing, judge) send no tools and no tool_choice
            payload |= {"tools": tools, "tool_choice": "auto"}
        data = await _post_with_retry(self._http, "/chat/completions", payload, self._provider,
                                      self.retry_statuses, self._max_retries)
        return parse_message(data["choices"][0]["message"])

    async def aclose(self) -> None:
        await self._http.aclose()


class GroqLLM(OpenAICompatibleChat):
    def __init__(self, api_key: str, model: str, http: httpx.AsyncClient | None = None, max_retries: int = 3):
        super().__init__(GROQ_BASE_URL, api_key, model, http=http, max_retries=max_retries, provider="groq")


def _text_of(content: Any) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    return "".join(p.get("text", "") for p in content if isinstance(p, dict) and p.get("type") == "text")


def to_anthropic_tools(tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for t in tools:
        fn = t["function"]
        out.append({"name": fn["name"], "description": fn.get("description", ""),
                    "input_schema": fn.get("parameters") or {"type": "object", "properties": {}}})
    return out


def to_anthropic_messages(messages: list[dict[str, Any]]) -> tuple[str, list[dict[str, Any]]]:
    """OpenAI chat messages -> (system text, Anthropic messages)."""
    system: list[str] = []
    out: list[dict[str, Any]] = []
    for m in messages:
        role = m["role"]
        if role == "system":
            system.append(_text_of(m.get("content")))
        elif role == "user":
            out.append({"role": "user", "content": _text_of(m.get("content"))})
        elif role == "assistant":
            blocks: list[dict[str, Any]] = []
            text = _text_of(m.get("content"))
            if text:
                blocks.append({"type": "text", "text": text})
            for tc in m.get("tool_calls") or []:
                raw = tc["function"].get("arguments") or "{}"
                try:
                    args = json.loads(raw) if isinstance(raw, str) else raw
                except json.JSONDecodeError:
                    args = {}
                blocks.append({"type": "tool_use", "id": tc["id"], "name": tc["function"]["name"],
                               "input": args if isinstance(args, dict) else {}})
            if blocks:
                out.append({"role": "assistant", "content": blocks})
        elif role == "tool":
            block = {"type": "tool_result", "tool_use_id": m["tool_call_id"], "content": _text_of(m.get("content"))}
            last = out[-1] if out else None
            if (last and last["role"] == "user" and isinstance(last["content"], list)
                    and all(b.get("type") == "tool_result" for b in last["content"])):
                last["content"].append(block)  # consecutive tool results share one user message
            else:
                out.append({"role": "user", "content": [block]})
        else:
            raise ValueError(f"Unsupported message role {role!r}")
    return "\n\n".join(s for s in system if s), out


def from_anthropic_response(data: dict[str, Any]) -> dict[str, Any]:
    """Anthropic response -> OpenAI-style assistant message."""
    text_parts: list[str] = []
    calls: list[dict[str, Any]] = []
    for block in data.get("content") or []:
        if block.get("type") == "text":
            text_parts.append(block.get("text", ""))
        elif block.get("type") == "tool_use":
            calls.append({"id": block["id"], "type": "function",
                          "function": {"name": block["name"], "arguments": json.dumps(block.get("input") or {})}})
    message: dict[str, Any] = {"role": "assistant", "content": "".join(text_parts) or None}
    if calls:
        message["tool_calls"] = calls
    return message


class AnthropicChat(ChatModel):
    """Anthropic Messages API over httpx, translated to and from the OpenAI chat-completions format."""

    retry_statuses = (429, 500, 502, 503, 529)

    def __init__(self, base_url: str, api_key: str | None, model: str, http: httpx.AsyncClient | None = None,
                 max_retries: int = 3, timeout: float = 60.0, max_tokens: int = 4096, provider: str = "anthropic"):
        self.kind = provider
        self.model = model
        self._provider = provider
        self._max_retries = max_retries
        self._max_tokens = max_tokens
        headers = {"x-api-key": api_key or "", "anthropic-version": ANTHROPIC_VERSION}
        self._http = http or httpx.AsyncClient(base_url=base_url.rstrip("/"), timeout=timeout, headers=headers)

    async def complete(self, messages, tools) -> LLMReply:
        system, converted = to_anthropic_messages(messages)
        # No temperature (current Claude models reject non-default sampling) and no forced tool_choice
        # (rejected on newer models); the default "auto" is what the agent loop needs.
        payload: dict[str, Any] = {"model": self.model, "max_tokens": self._max_tokens, "messages": converted}
        if system:
            payload["system"] = system
        if tools:
            payload["tools"] = to_anthropic_tools(tools)
        data = await _post_with_retry(self._http, "/messages", payload, self._provider,
                                      self.retry_statuses, self._max_retries)
        if data.get("stop_reason") == "refusal":
            raise RuntimeError(f"{self._provider} declined the request (stop_reason=refusal)")
        return parse_message(from_anthropic_response(data))

    async def aclose(self) -> None:
        await self._http.aclose()


@dataclass(frozen=True)
class ProviderSpec:
    name: str
    adapter: type[ChatModel]
    base_url: str | None  # None: LLM_BASE_URL is required
    key_required: bool = True


PROVIDERS: dict[str, ProviderSpec] = {
    s.name: s for s in (
        ProviderSpec("groq", OpenAICompatibleChat, GROQ_BASE_URL),
        ProviderSpec("nvidia", OpenAICompatibleChat, NVIDIA_BASE_URL),
        ProviderSpec("openai", OpenAICompatibleChat, "https://api.openai.com/v1"),
        ProviderSpec("openrouter", OpenAICompatibleChat, "https://openrouter.ai/api/v1"),
        ProviderSpec("together", OpenAICompatibleChat, "https://api.together.xyz/v1"),
        ProviderSpec("ollama", OpenAICompatibleChat, "http://localhost:11434/v1", key_required=False),
        ProviderSpec("anthropic", AnthropicChat, ANTHROPIC_BASE_URL),
        ProviderSpec("openai-compatible", OpenAICompatibleChat, None),
    )
}


@dataclass(frozen=True)
class LLMSettings:
    provider: str
    model: str
    api_key: str | None
    base_url: str


def _env(name: str) -> str:
    return os.getenv(name, "").strip()


def load_llm_settings() -> LLMSettings:
    """Read the live LLM configuration from the environment now. Raises LLMConfigError naming what is missing."""
    provider = _env("LLM_PROVIDER").lower()
    if not provider:
        if _env("GROQ_API_KEY") and _env("GROQ_MODEL"):
            return LLMSettings("groq", _env("GROQ_MODEL"), _env("GROQ_API_KEY"), _env("LLM_BASE_URL") or GROQ_BASE_URL)
        raise LLMConfigError("Live LLM is not configured. Set LLM_PROVIDER, LLM_MODEL and LLM_API_KEY in .env "
                             "(or GROQ_API_KEY and GROQ_MODEL), or use --llm mock")
    spec = PROVIDERS.get(provider)
    if spec is None:
        raise LLMConfigError(f"Unknown LLM_PROVIDER {provider!r}; use one of: {', '.join(sorted(PROVIDERS))}")
    legacy = provider == "groq"  # GROQ_* keep working for the groq provider
    model = _env("LLM_MODEL") or (_env("GROQ_MODEL") if legacy else "")
    if not model:
        raise LLMConfigError(f"LLM_PROVIDER={provider} needs LLM_MODEL (the model id) in .env")
    api_key = _env("LLM_API_KEY") or (_env("GROQ_API_KEY") if legacy else "")
    if spec.key_required and not api_key:
        raise LLMConfigError(f"LLM_PROVIDER={provider} needs LLM_API_KEY in .env")
    base_url = _env("LLM_BASE_URL") or spec.base_url
    if not base_url:
        raise LLMConfigError(f"LLM_PROVIDER={provider} needs LLM_BASE_URL in .env")
    return LLMSettings(provider, model, api_key or None, base_url)


def build_live_llm() -> ChatModel:
    s = load_llm_settings()
    return PROVIDERS[s.provider].adapter(base_url=s.base_url, api_key=s.api_key, model=s.model, provider=s.provider)


def live_llm_configured() -> bool:
    try:
        load_llm_settings()
    except LLMConfigError:
        return False
    return True


def live_llm_label() -> str | None:
    try:
        s = load_llm_settings()
    except LLMConfigError:
        return None
    return f"{s.provider}:{s.model}"


groq_configured = live_llm_configured  # old name, still imported by callers


class ReplayLLM(ChatModel):
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


class RecordingLLM(ChatModel):
    """Wraps a live LLM and saves every reply as a cassette, so a live run can be replayed in tests."""

    def __init__(self, inner: ChatModel, path: Path):
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
        await close_llm(self._inner)


def resolve_cassette(name: str) -> Path:
    """Cassettes are referenced by name only (no paths), e.g. 'day2_flaws_on'."""
    if not name.replace("_", "").replace("-", "").isalnum():
        raise LLMConfigError(f"Invalid cassette name {name!r}")
    path = CASSETTE_DIR / f"{name}.json"
    if not path.is_file():
        available = ", ".join(sorted(p.stem for p in CASSETTE_DIR.glob("*.json")))
        raise LLMConfigError(f"No cassette {name!r}. Available: {available}")
    return path


def make_llm(kind: str, cassette: str | None = None, record_to: Path | None = None) -> ChatModel:
    """kind is 'live' (the configured provider; 'groq' is an alias) or 'mock' (replay a cassette)."""
    if kind == "mock":
        if not cassette:
            raise LLMConfigError("Mock LLM needs a cassette name")
        return ReplayLLM(resolve_cassette(cassette))
    if kind in ("live", "groq"):
        llm = build_live_llm()
        return RecordingLLM(llm, record_to) if record_to else llm
    raise LLMConfigError(f"Unknown LLM kind {kind!r}; use 'live' (or 'groq') or 'mock'")
