"""ローカル LLM クライアント（OpenAI 互換 API）。

LM Studio / Ollama / llama.cpp などが提供する OpenAI 互換エンドポイント
（``{base_url}/chat/completions``）へ POST する。Gemini 系が枯渇/障害のときの
最終フォールバックとして使う。
"""

from typing import Any

import httpx

from thesis_ai.llm.base import (
    LLMError,
    Message,
    RateLimitError,
    TransientLLMError,
)

_ROLE_MAP = {"system": "system", "user": "user", "model": "assistant", "assistant": "assistant"}


def _to_openai_message(message: Message) -> dict[str, str]:
    return {"role": _ROLE_MAP.get(message.role, "user"), "content": message.content}


class LocalLLMClient:
    """OpenAI 互換のローカル LLM を呼び出すクライアント。"""

    def __init__(
        self,
        client: httpx.AsyncClient,
        *,
        base_url: str,
        model: str,
    ) -> None:
        self._client = client
        self._url = base_url.rstrip("/") + "/chat/completions"
        self._model = model

    async def generate(self, messages: list[Message], *, max_tokens: int = 2048) -> str:
        payload: dict[str, Any] = {
            "model": self._model,
            "messages": [_to_openai_message(m) for m in messages],
            "max_tokens": max_tokens,
        }
        try:
            resp = await self._client.post(self._url, json=payload)
        except httpx.HTTPError as exc:
            raise TransientLLMError(str(exc)) from exc

        if resp.status_code == 429:
            raise RateLimitError("local LLM rate limited")
        if resp.is_server_error:
            raise TransientLLMError(f"local LLM server error: {resp.status_code}")
        if resp.is_error:
            raise LLMError(f"local LLM error: {resp.status_code}")

        text = _extract_content(resp)
        if not text:
            raise LLMError("empty response from local LLM")
        return text


def _extract_content(resp: httpx.Response) -> str:
    """OpenAI 互換レスポンスから本文を取り出す。形式不正は LLMError。"""
    try:
        data = resp.json()
        content = data["choices"][0]["message"]["content"]
    except (ValueError, KeyError, IndexError, TypeError) as exc:
        raise LLMError("malformed response from local LLM") from exc
    if not isinstance(content, str):
        raise LLMError("unexpected content type from local LLM")
    return content.strip()
