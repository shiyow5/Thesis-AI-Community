"""Gemini API クライアント。Gemma 4 / Gemini 2.5 Flash を同一実装で扱う。

モデル名を引数化することで、無料枠の大きい Gemma 4 と品質重視の Gemini 2.5 Flash を
同じコードパスで呼び分ける。
"""

import logging
from typing import Any

import httpx
from google import genai
from google.genai import errors, types

from thesis_ai.llm.base import (
    LLMError,
    Message,
    RateLimitError,
    TransientLLMError,
)

logger = logging.getLogger(__name__)

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
        thinking_budget: int | None = None,
    ) -> None:
        self._client = client or genai.Client(api_key=api_key)
        self._model = model
        self._thinking_budget = thinking_budget

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
        config_kwargs: dict[str, Any] = {
            "system_instruction": system,
            "max_output_tokens": max_tokens,
        }
        # Gemini 2.5 系は thinking が max_output_tokens を消費し可視出力が切れるため、
        # thinking_budget=0 で無効化する。Gemma 4 も thinking モデルだが thinking_budget の
        # 指定自体が 400 INVALID_ARGUMENT になる（無効化不可）ため None のまま呼び、思考分は
        # 呼び出し側が max_tokens に余裕を持たせて吸収する。
        if self._thinking_budget is not None:
            config_kwargs["thinking_config"] = types.ThinkingConfig(
                thinking_budget=self._thinking_budget
            )
        config = types.GenerateContentConfig(**config_kwargs)

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
            # thinking モデル（Gemma 4 等）は思考トークンが max_output_tokens を使い切ると
            # finish_reason=MAX_TOKENS で可視テキストが出ず空になる。原因追跡のため詳細を残す。
            candidates = getattr(resp, "candidates", None) or []
            finish_reason = getattr(candidates[0], "finish_reason", None) if candidates else None
            usage = getattr(resp, "usage_metadata", None)
            thoughts = getattr(usage, "thoughts_token_count", None) if usage else None
            logger.warning(
                "Gemini 空応答: model=%s finish_reason=%s thoughts_tokens=%s max_tokens=%s",
                self._model,
                finish_reason,
                thoughts,
                max_tokens,
            )
            raise LLMError(f"empty response from Gemini (finish_reason={finish_reason})")
        return text
