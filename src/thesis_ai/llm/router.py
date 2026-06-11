"""複数 LLM を束ねるルーター。レート制御とフォールバックを担う。

- 各モデルに per-minute / per-day のスライディングウィンドウ制限を課す
- ローカル枠超過 / 429 のモデルは次段へフォールバック
- 一時的エラー（5xx 等）は指数バックオフで同一モデルをリトライ
"""

import asyncio
import time
from collections import deque
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from thesis_ai.llm.base import (
    LLMClient,
    LLMError,
    Message,
    RateLimitError,
    TransientLLMError,
)

Clock = Callable[[], float]
Sleeper = Callable[[float], Awaitable[None]]

_SECONDS_PER_MINUTE = 60.0
_SECONDS_PER_DAY = 86_400.0


class SlidingRateLimiter:
    """分次・日次のスライディングウィンドウによるレート制御。"""

    def __init__(
        self,
        *,
        max_per_minute: int,
        max_per_day: int,
        clock: Clock | None = None,
    ) -> None:
        self._rpm = max_per_minute
        self._rpd = max_per_day
        self._clock = clock or time.monotonic
        self._minute: deque[float] = deque()
        self._day: deque[float] = deque()

    def _evict(self, now: float) -> None:
        while self._minute and now - self._minute[0] >= _SECONDS_PER_MINUTE:
            self._minute.popleft()
        while self._day and now - self._day[0] >= _SECONDS_PER_DAY:
            self._day.popleft()

    def allow(self) -> bool:
        """1 リクエスト分の枠を取得できれば True を返し、消費する。"""
        now = self._clock()
        self._evict(now)
        if len(self._minute) >= self._rpm or len(self._day) >= self._rpd:
            return False
        self._minute.append(now)
        self._day.append(now)
        return True


@dataclass
class RoutedModel:
    """ルーターのチェーンを構成する 1 モデル。"""

    name: str
    client: LLMClient
    limiter: SlidingRateLimiter


class LLMRouter:
    """チェーン先頭から順にレート枠を確認しつつフォールバックする。"""

    def __init__(
        self,
        chain: list[RoutedModel],
        *,
        max_retries: int = 2,
        backoff_base: float = 1.0,
        sleep: Sleeper | None = None,
    ) -> None:
        if not chain:
            raise ValueError("chain must contain at least one model")
        self._chain = chain
        self._max_retries = max_retries
        self._backoff_base = backoff_base
        self._sleep = sleep or asyncio.sleep

    async def generate(self, messages: list[Message], *, max_tokens: int = 2048) -> str:
        """チェーンに沿って生成を試み、成功した最初の結果を返す。"""
        last_error: LLMError = LLMError("no model available")

        for model in self._chain:
            if not model.limiter.allow():
                last_error = RateLimitError(f"{model.name}: local rate limit reached")
                continue

            for attempt in range(self._max_retries + 1):
                try:
                    return await model.client.generate(messages, max_tokens=max_tokens)
                except RateLimitError as exc:
                    last_error = exc
                    break  # このモデルは枠切れ → 次のモデルへ
                except TransientLLMError as exc:
                    last_error = exc
                    if attempt < self._max_retries:
                        await self._sleep(self._backoff_base * (2**attempt))
                        continue
                    break  # リトライ尽きた → 次のモデルへ
                except LLMError as exc:
                    last_error = exc
                    break  # 非リトライ系 → 次のモデルへ

        raise last_error
