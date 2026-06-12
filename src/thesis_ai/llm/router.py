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

# レート制限(429)時に同一モデルを待って再試行する際の既定待機秒と上限。
# Gemma の TPM(トークン/分)枠は 60 秒で回復するため、その範囲で待ち直す。
_DEFAULT_RATE_LIMIT_WAIT = 20.0
_MAX_RATE_LIMIT_WAIT = 60.0


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


def _rate_limit_wait(model: "RoutedModel", exc: RateLimitError) -> float:
    """429 後に待つ秒数を決める。retry_after を優先し、上限でクランプする。"""
    wait = exc.retry_after if exc.retry_after is not None else model.rate_limit_wait
    return min(wait, _MAX_RATE_LIMIT_WAIT)


@dataclass
class RoutedModel:
    """ルーターのチェーンを構成する 1 モデル。

    ``rate_limit_retries`` を 1 以上にすると、429 で即フォールバックせず
    ``rate_limit_wait`` 秒（``retry_after`` があればそれを優先、上限 60 秒）待って
    同一モデルを再試行する。無料・高品質な主力モデルを使い切るための設定。
    """

    name: str
    client: LLMClient
    limiter: SlidingRateLimiter
    rate_limit_retries: int = 0
    rate_limit_wait: float = _DEFAULT_RATE_LIMIT_WAIT


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

            transient_left = self._max_retries
            rate_limit_left = model.rate_limit_retries
            while True:
                try:
                    return await model.client.generate(messages, max_tokens=max_tokens)
                except RateLimitError as exc:
                    last_error = exc
                    if rate_limit_left <= 0:
                        break  # 再試行枠を使い切った → 次のモデルへ
                    rate_limit_left -= 1
                    await self._sleep(_rate_limit_wait(model, exc))
                    continue  # TPM 回復を待って同一モデルを再試行
                except TransientLLMError as exc:
                    last_error = exc
                    if transient_left <= 0:
                        break  # リトライ尽きた → 次のモデルへ
                    attempt = self._max_retries - transient_left
                    transient_left -= 1
                    await self._sleep(self._backoff_base * (2**attempt))
                    continue
                except LLMError as exc:
                    last_error = exc
                    break  # 非リトライ系 → 次のモデルへ

        raise last_error
