"""Provider adapters, registry and env configuration. No network: httpx.MockTransport only."""

import json
from types import SimpleNamespace

import httpx
import pytest

from backend.app.agent import llm as llm_mod
from backend.app.agent.llm import (
    PROVIDERS,
    AnthropicChat,
    ChatModel,
    LLMConfigError,
    OpenAICompatibleChat,
    RecordingLLM,
    live_llm_configured,
    live_llm_label,
    load_llm_settings,
    make_llm,
)

TOOLS = [{"type": "function", "function": {"name": "click", "description": "Click an element",
                                           "parameters": {"type": "object", "properties": {"element_id": {"type": "string"}},
                                                          "required": ["element_id"]}}}]
ENV_VARS = ["LLM_PROVIDER", "LLM_MODEL", "LLM_API_KEY", "LLM_BASE_URL", "GROQ_API_KEY", "GROQ_MODEL"]


@pytest.fixture
def clean_env(monkeypatch):
    for name in ENV_VARS:
        monkeypatch.delenv(name, raising=False)
    return monkeypatch


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    async def instant(_):
        return None

    monkeypatch.setattr(llm_mod, "asyncio", SimpleNamespace(sleep=instant))


def client(handler, base_url, headers=None):
    return httpx.AsyncClient(base_url=base_url, transport=httpx.MockTransport(handler), headers=headers or {})


# --- OpenAI-compatible ------------------------------------------------------------------------------


@pytest.mark.anyio
async def test_openai_compatible_request_and_tool_calls():
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        msg = {"role": "assistant", "content": None, "tool_calls": [
            {"id": "c1", "type": "function", "function": {"name": "click", "arguments": '{"element_id": "e3"}'}}]}
        return httpx.Response(200, json={"choices": [{"message": msg}]})

    http = client(handler, "https://llm.test/v1", {"Authorization": "Bearer k"})
    model = OpenAICompatibleChat("https://llm.test/v1", "k", "m1", http=http)
    reply = await model.complete([{"role": "user", "content": "hi"}], TOOLS)
    req = seen[0]
    body = json.loads(req.content)
    assert str(req.url) == "https://llm.test/v1/chat/completions"
    assert req.headers["authorization"] == "Bearer k"
    assert body["model"] == "m1" and body["tools"] == TOOLS and body["tool_choice"] == "auto"
    assert reply.tool_calls[0].name == "click" and reply.tool_calls[0].arguments == {"element_id": "e3"}


@pytest.mark.anyio
async def test_openai_compatible_sets_auth_header_on_its_own_client():
    model = OpenAICompatibleChat("https://llm.test/v1/", "secret-key", "m1")
    assert model._http.headers["authorization"] == "Bearer secret-key"
    assert str(model._http.base_url).rstrip("/") == "https://llm.test/v1"
    await model.aclose()


@pytest.mark.anyio
async def test_openai_compatible_retries_429_then_succeeds():
    n = {"calls": 0}

    def handler(request):
        n["calls"] += 1
        if n["calls"] == 1:
            return httpx.Response(429, headers={"retry-after": "1"})
        return httpx.Response(200, json={"choices": [{"message": {"role": "assistant", "content": "ok"}}]})

    model = OpenAICompatibleChat("https://llm.test/v1", None, "m1", http=client(handler, "https://llm.test/v1"))
    reply = await model.complete([{"role": "user", "content": "hi"}], [])
    assert n["calls"] == 2 and reply.content == "ok"


@pytest.mark.anyio
async def test_openai_compatible_sends_no_tools_keys_when_empty():
    bodies = []

    def handler(request):
        bodies.append(json.loads(request.content))
        return httpx.Response(200, json={"choices": [{"message": {"role": "assistant", "content": "ok"}}]})

    model = OpenAICompatibleChat("https://llm.test/v1", None, "m1", http=client(handler, "https://llm.test/v1"))
    await model.complete([{"role": "user", "content": "hi"}], [])
    assert "tools" not in bodies[0] and "tool_choice" not in bodies[0]


@pytest.mark.anyio
async def test_error_names_provider_and_never_the_key():
    def handler(request):
        return httpx.Response(401, text="bad credentials")

    model = OpenAICompatibleChat("https://llm.test/v1", "super-secret", "m1", provider="openrouter",
                                 http=client(handler, "https://llm.test/v1"))
    with pytest.raises(RuntimeError) as err:
        await model.complete([{"role": "user", "content": "hi"}], [])
    assert "openrouter" in str(err.value) and "super-secret" not in str(err.value)


# --- Anthropic --------------------------------------------------------------------------------------

HISTORY = [
    {"role": "system", "content": "You are a shopper."},
    {"role": "user", "content": "Buy the mug."},
    {"role": "assistant", "content": "Looking.", "tool_calls": [
        {"id": "t1", "type": "function", "function": {"name": "click", "arguments": '{"element_id": "e1"}'}},
        {"id": "t2", "type": "function", "function": {"name": "click", "arguments": '{"element_id": "e2"}'}}]},
    {"role": "tool", "tool_call_id": "t1", "content": "page one"},
    {"role": "tool", "tool_call_id": "t2", "content": "page two"},
]


@pytest.mark.anyio
async def test_anthropic_request_translation():
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"content": [{"type": "text", "text": "done"}], "stop_reason": "end_turn"})

    http = client(handler, "https://api.anthropic.test/v1", {"x-api-key": "k", "anthropic-version": "2023-06-01"})
    model = AnthropicChat("https://api.anthropic.test/v1", "k", "claude-test", http=http)
    await model.complete(HISTORY, TOOLS)
    req = seen[0]
    body = json.loads(req.content)
    assert str(req.url) == "https://api.anthropic.test/v1/messages"
    assert req.headers["x-api-key"] == "k" and req.headers["anthropic-version"] == "2023-06-01"
    assert body["model"] == "claude-test" and body["max_tokens"] > 0
    assert body["system"] == "You are a shopper."
    assert body["tools"] == [{"name": "click", "description": "Click an element",
                              "input_schema": TOOLS[0]["function"]["parameters"]}]
    assert "tool_choice" not in body and "temperature" not in body
    assert [m["role"] for m in body["messages"]] == ["user", "assistant", "user"]
    assert body["messages"][0]["content"] == "Buy the mug."
    assert body["messages"][1]["content"] == [
        {"type": "text", "text": "Looking."},
        {"type": "tool_use", "id": "t1", "name": "click", "input": {"element_id": "e1"}},
        {"type": "tool_use", "id": "t2", "name": "click", "input": {"element_id": "e2"}}]
    assert body["messages"][2]["content"] == [
        {"type": "tool_result", "tool_use_id": "t1", "content": "page one"},
        {"type": "tool_result", "tool_use_id": "t2", "content": "page two"}]


@pytest.mark.anyio
async def test_anthropic_response_translation_and_no_tools_key():
    bodies = []

    def handler(request):
        bodies.append(json.loads(request.content))
        return httpx.Response(200, json={"stop_reason": "tool_use", "content": [
            {"type": "text", "text": "Clicking."},
            {"type": "tool_use", "id": "toolu_1", "name": "click", "input": {"element_id": "e9"}}]})

    model = AnthropicChat("https://a.test/v1", "k", "m", http=client(handler, "https://a.test/v1"))
    reply = await model.complete([{"role": "user", "content": "go"}], TOOLS)
    assert reply.content == "Clicking."
    assert reply.tool_calls[0].id == "toolu_1" and reply.tool_calls[0].arguments == {"element_id": "e9"}
    call = reply.message["tool_calls"][0]
    assert call["type"] == "function" and json.loads(call["function"]["arguments"]) == {"element_id": "e9"}

    await model.complete([{"role": "user", "content": "just text"}], [])
    assert "tools" not in bodies[1] and "system" not in bodies[1]


@pytest.mark.anyio
async def test_anthropic_text_reply():
    def handler(request):
        return httpx.Response(200, json={"stop_reason": "end_turn", "content": [{"type": "text", "text": "hello"}]})

    model = AnthropicChat("https://a.test/v1", "k", "m", http=client(handler, "https://a.test/v1"))
    reply = await model.complete([{"role": "user", "content": "hi"}], [])
    assert reply.content == "hello" and reply.tool_calls == [] and "tool_calls" not in reply.message


@pytest.mark.anyio
async def test_anthropic_retries_529():
    n = {"calls": 0}

    def handler(request):
        n["calls"] += 1
        if n["calls"] == 1:
            return httpx.Response(529, json={"error": {"type": "overloaded_error"}})
        return httpx.Response(200, json={"stop_reason": "end_turn", "content": [{"type": "text", "text": "ok"}]})

    model = AnthropicChat("https://a.test/v1", "k", "m", http=client(handler, "https://a.test/v1"))
    reply = await model.complete([{"role": "user", "content": "hi"}], [])
    assert n["calls"] == 2 and reply.content == "ok"


# --- Registry and environment -----------------------------------------------------------------------


@pytest.mark.parametrize("name", ["groq", "nvidia", "openai", "openrouter", "together", "ollama", "anthropic"])
def test_each_provider_resolves(clean_env, name):
    clean_env.setenv("LLM_PROVIDER", name)
    clean_env.setenv("LLM_MODEL", "some-model")
    clean_env.setenv("LLM_API_KEY", "k")
    model = make_llm("live")
    assert isinstance(model, ChatModel) and model.kind == name and model.model == "some-model"
    assert isinstance(model, AnthropicChat if name == "anthropic" else OpenAICompatibleChat)
    assert live_llm_label() == f"{name}:some-model"
    assert live_llm_configured()


def test_nvidia_provider_uses_the_nvidia_endpoint(clean_env):
    clean_env.setenv("LLM_PROVIDER", "nvidia")
    clean_env.setenv("LLM_MODEL", "nvidia/nemotron")
    clean_env.setenv("LLM_API_KEY", "k")
    assert load_llm_settings().base_url == "https://integrate.api.nvidia.com/v1"


def test_openai_compatible_requires_base_url(clean_env):
    clean_env.setenv("LLM_PROVIDER", "openai-compatible")
    clean_env.setenv("LLM_MODEL", "m")
    clean_env.setenv("LLM_API_KEY", "k")
    with pytest.raises(LLMConfigError, match="LLM_BASE_URL"):
        make_llm("live")
    assert not live_llm_configured() and live_llm_label() is None
    clean_env.setenv("LLM_BASE_URL", "http://localhost:8080/v1")
    assert make_llm("live").kind == "openai-compatible"


def test_ollama_needs_no_key(clean_env):
    clean_env.setenv("LLM_PROVIDER", "ollama")
    clean_env.setenv("LLM_MODEL", "llama3")
    model = make_llm("live")
    assert str(model._http.base_url).rstrip("/") == "http://localhost:11434/v1"
    assert "authorization" not in model._http.headers


def test_groq_env_backward_compatible(clean_env):
    clean_env.setenv("GROQ_API_KEY", "gk")
    clean_env.setenv("GROQ_MODEL", "gm")
    assert live_llm_configured() and live_llm_label() == "groq:gm"
    model = make_llm("groq")  # alias of live
    assert model.kind == "groq" and model.model == "gm"
    assert model._http.headers["authorization"] == "Bearer gk"


def test_explicit_config_errors(clean_env):
    with pytest.raises(LLMConfigError, match="LLM_PROVIDER"):
        make_llm("live")
    clean_env.setenv("LLM_PROVIDER", "nope")
    with pytest.raises(LLMConfigError, match="Unknown LLM_PROVIDER"):
        make_llm("live")
    clean_env.setenv("LLM_PROVIDER", "openai")
    with pytest.raises(LLMConfigError, match="LLM_MODEL"):
        make_llm("live")
    clean_env.setenv("LLM_MODEL", "m")
    with pytest.raises(LLMConfigError, match="LLM_API_KEY"):
        make_llm("live")
    with pytest.raises(LLMConfigError, match="Unknown LLM kind"):
        make_llm("bogus")


def test_registry_has_required_providers():
    assert {"groq", "openai", "openrouter", "together", "ollama", "anthropic", "openai-compatible"} <= set(PROVIDERS)
    assert PROVIDERS["openai-compatible"].base_url is None and not PROVIDERS["ollama"].key_required


@pytest.mark.anyio
async def test_context_manager_and_recording_close(clean_env, tmp_path):
    closed = []

    class Fake(ChatModel):
        kind = "fake"
        model = "m"

        async def complete(self, messages, tools):
            raise NotImplementedError

        async def aclose(self):
            closed.append(True)

    async with RecordingLLM(Fake(), tmp_path / "c.json"):
        pass
    assert closed == [True]
