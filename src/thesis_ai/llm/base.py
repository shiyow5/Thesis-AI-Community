"""LLM クライアントの共通インターフェースとエラー型。"""

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class Message:
    """LLM への 1 メッセージ。role は ``system`` / ``user`` / ``model``。"""

    role: str
    content: str


class LLMError(Exception):
    """LLM 呼び出しの一般エラー。"""


class TransientLLMError(LLMError):
    """一時的でリトライ可能なエラー（5xx・タイムアウト等）。"""


class RateLimitError(LLMError):
    """レート制限（429）。``retry_after`` は秒単位の待機推奨時間。"""

    def __init__(self, message: str = "", *, retry_after: float | None = None) -> None:
        super().__init__(message)
        self.retry_after = retry_after


class LLMClient(Protocol):
    """テキスト生成を行う LLM クライアントの構造的インターフェース。"""

    async def generate(self, messages: list[Message], *, max_tokens: int) -> str: ...
