"""LocalLLMClient（OpenAI 互換）のテスト。"""

import httpx
import pytest
import respx

from thesis_ai.llm.base import LLMError, Message, RateLimitError, TransientLLMError
from thesis_ai.llm.local import LocalLLMClient

BASE_URL = "http://localhost:1234/v1"
ENDPOINT = "http://localhost:1234/v1/chat/completions"

_MSGS = [
    Message(role="system", content="be brief"),
    Message(role="user", content="hi"),
    Message(role="model", content="prev"),
]


def _client(http: httpx.AsyncClient) -> LocalLLMClient:
    return LocalLLMClient(http, base_url=BASE_URL, model="lfm2")


def _ok(text: str = "ローカル応答") -> dict[str, object]:
    return {"choices": [{"message": {"role": "assistant", "content": text}}]}


@respx.mock
async def test_generate_returns_content_and_maps_roles() -> None:
    route = respx.post(ENDPOINT).mock(return_value=httpx.Response(200, json=_ok()))

    async with httpx.AsyncClient() as http:
        result = await _client(http).generate(_MSGS, max_tokens=64)

    assert result == "ローカル応答"
    sent = route.calls.last.request
    import json

    body = json.loads(sent.read())
    assert body["model"] == "lfm2"
    assert body["max_tokens"] == 64
    # model ロールは assistant に変換される
    roles = [m["role"] for m in body["messages"]]
    assert roles == ["system", "user", "assistant"]


@respx.mock
async def test_empty_content_raises_llm_error() -> None:
    respx.post(ENDPOINT).mock(return_value=httpx.Response(200, json=_ok("")))

    async with httpx.AsyncClient() as http:
        with pytest.raises(LLMError, match="empty"):
            await _client(http).generate(_MSGS)


@respx.mock
async def test_malformed_response_raises_llm_error() -> None:
    respx.post(ENDPOINT).mock(return_value=httpx.Response(200, json={"unexpected": 1}))

    async with httpx.AsyncClient() as http:
        with pytest.raises(LLMError, match="malformed"):
            await _client(http).generate(_MSGS)


@respx.mock
async def test_429_maps_to_rate_limit() -> None:
    respx.post(ENDPOINT).mock(return_value=httpx.Response(429))

    async with httpx.AsyncClient() as http:
        with pytest.raises(RateLimitError):
            await _client(http).generate(_MSGS)


@respx.mock
async def test_500_maps_to_transient() -> None:
    respx.post(ENDPOINT).mock(return_value=httpx.Response(500))

    async with httpx.AsyncClient() as http:
        with pytest.raises(TransientLLMError):
            await _client(http).generate(_MSGS)


@respx.mock
async def test_400_maps_to_generic_error() -> None:
    respx.post(ENDPOINT).mock(return_value=httpx.Response(400))

    async with httpx.AsyncClient() as http:
        with pytest.raises(LLMError) as excinfo:
            await _client(http).generate(_MSGS)
        assert not isinstance(excinfo.value, (RateLimitError, TransientLLMError))


@respx.mock
async def test_network_error_maps_to_transient() -> None:
    respx.post(ENDPOINT).mock(side_effect=httpx.ConnectError("refused"))

    async with httpx.AsyncClient() as http:
        with pytest.raises(TransientLLMError):
            await _client(http).generate(_MSGS)
