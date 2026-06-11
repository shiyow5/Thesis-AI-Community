"""GeminiClient とエラーマッピングのテスト（API は呼ばずフェイク注入）。"""

from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock

import pytest
from google import genai
from google.genai import errors

from thesis_ai.llm.base import LLMError, Message, RateLimitError, TransientLLMError
from thesis_ai.llm.gemini import GeminiClient, _map_api_error


def _fake_client(
    *, text: str | None = None, exc: Exception | None = None
) -> tuple[genai.Client, AsyncMock]:
    gen = AsyncMock()
    if exc is not None:
        gen.side_effect = exc
    else:
        gen.return_value = SimpleNamespace(text=text)
    fake = SimpleNamespace(aio=SimpleNamespace(models=SimpleNamespace(generate_content=gen)))
    return cast(genai.Client, fake), gen


_MSGS = [Message(role="system", content="be brief"), Message(role="user", content="hi")]


async def test_generate_returns_text_and_uses_model() -> None:
    client, gen = _fake_client(text="hello")
    gemini = GeminiClient(api_key="x", model="gemma-4", client=client)

    result = await gemini.generate(_MSGS, max_tokens=128)

    assert result == "hello"
    assert gen.await_args is not None
    assert gen.await_args.kwargs["model"] == "gemma-4"
    # system メッセージは contents から除外される
    assert len(gen.await_args.kwargs["contents"]) == 1
    # thinking_budget 未指定なら thinking_config は付かない
    assert gen.await_args.kwargs["config"].thinking_config is None


async def test_thinking_budget_disables_thinking() -> None:
    client, gen = _fake_client(text="ok")
    gemini = GeminiClient(api_key="x", model="gemini-2.5-flash", client=client, thinking_budget=0)

    await gemini.generate(_MSGS)

    assert gen.await_args is not None
    config = gen.await_args.kwargs["config"]
    assert config.thinking_config is not None
    assert config.thinking_config.thinking_budget == 0


async def test_empty_response_raises_llm_error() -> None:
    client, _ = _fake_client(text=None)
    gemini = GeminiClient(api_key="x", model="gemma-4", client=client)

    with pytest.raises(LLMError, match="empty response"):
        await gemini.generate(_MSGS)


async def test_rate_limit_error_mapped() -> None:
    client, _ = _fake_client(exc=errors.ClientError(429, {"error": {"message": "quota"}}))
    gemini = GeminiClient(api_key="x", model="gemma-4", client=client)

    with pytest.raises(RateLimitError):
        await gemini.generate(_MSGS)


async def test_server_error_mapped_to_transient() -> None:
    client, _ = _fake_client(exc=errors.ServerError(503, {"error": {"message": "down"}}))
    gemini = GeminiClient(api_key="x", model="gemma-4", client=client)

    with pytest.raises(TransientLLMError):
        await gemini.generate(_MSGS)


def test_map_api_error_client_400_is_generic() -> None:
    mapped = _map_api_error(errors.ClientError(400, {"error": {"message": "bad"}}))

    assert isinstance(mapped, LLMError)
    assert not isinstance(mapped, RateLimitError | TransientLLMError)


def test_map_api_error_429_is_rate_limit() -> None:
    assert isinstance(
        _map_api_error(errors.ClientError(429, {"error": {"message": "x"}})), RateLimitError
    )


def test_map_api_error_server_is_transient() -> None:
    assert isinstance(
        _map_api_error(errors.ServerError(500, {"error": {"message": "x"}})), TransientLLMError
    )
