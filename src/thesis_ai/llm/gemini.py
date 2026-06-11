"""Gemini API クライアント。Gemma 4 / Gemini 2.5 Flash を同一実装で扱う。

モデル名を引数化することで、無料枠の大きい Gemma 4 と品質重視の Gemini 2.5 Flash を
同じコードパスで呼び分ける。
"""

import httpx
from google import genai
from google.genai import errors, types

from thesis_ai.llm.base import (
    LLMError,
    Message,
    RateLimitError,
    TransientLLMError,
)

_ROLE_MAP = {"user": "user", "model": "model", "assistant": "model"}


def _map_api_error(exc: errors.APIError) -> LLMError:
    """google-genai の APIError を内部エラー型へ変換する。"""
    if isinstance(exc, errors.ServerError):
        return TransientLLMError(str(exc))
    code = getattr(exc, "code", None)
    if code == 429:
        return RateLimitError(str(exc))
    return LLMError(str(exc))


class GeminiClient:
    """Gemini API 経由でテキスト生成を行うクライアント。"""

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        client: genai.Client | None = None,
    ) -> None:
        self._client = client or genai.Client(api_key=api_key)
        self._model = model

    async def generate(self, messages: list[Message], *, max_tokens: int = 2048) -> str:
        system = "\n\n".join(m.content for m in messages if m.role == "system") or None
        contents = [
            types.Content(
                role=_ROLE_MAP.get(m.role, "user"),
                parts=[types.Part(text=m.content)],
            )
            for m in messages
            if m.role != "system"
        ]
        config = types.GenerateContentConfig(
            system_instruction=system,
            max_output_tokens=max_tokens,
        )

        try:
            resp = await self._client.aio.models.generate_content(
                model=self._model,
                contents=contents,
                config=config,
            )
        except errors.APIError as exc:
            raise _map_api_error(exc) from exc
        except httpx.HTTPError as exc:
            raise TransientLLMError(str(exc)) from exc

        text = resp.text
        if not text:
            raise LLMError("empty response from Gemini")
        return text
