"""LLMRouter と SlidingRateLimiter のテスト。"""

import pytest

from thesis_ai.llm.base import (
    LLMError,
    Message,
    RateLimitError,
    TransientLLMError,
)
from thesis_ai.llm.router import (
    LLMRouter,
    RoutedModel,
    SlidingRateLimiter,
)


class FakeClient:
    """テスト用 LLMClient。順に例外を投げ、最後にテキストを返す。"""

    def __init__(self, *, text: str = "ok", errors: list[Exception] | None = None) -> None:
        self._text = text
        self._errors = list(errors or [])
        self.calls = 0

    async def generate(self, messages: list[Message], *, max_tokens: int) -> str:
        self.calls += 1
        if self._errors:
            raise self._errors.pop(0)
        return self._text


def _open_limiter() -> SlidingRateLimiter:
    return SlidingRateLimiter(max_per_minute=100, max_per_day=1000)


def _model(name: str, client: FakeClient, limiter: SlidingRateLimiter | None = None) -> RoutedModel:
    return RoutedModel(name=name, client=client, limiter=limiter or _open_limiter())


_MSGS = [Message(role="user", content="hi")]


async def test_returns_first_model_result() -> None:
    primary = FakeClient(text="primary")
    secondary = FakeClient(text="secondary")
    router = LLMRouter([_model("a", primary), _model("b", secondary)])

    result = await router.generate(_MSGS)

    assert result == "primary"
    assert secondary.calls == 0


async def test_falls_back_when_local_limit_reached() -> None:
    primary = FakeClient(text="primary")
    secondary = FakeClient(text="secondary")
    blocked = SlidingRateLimiter(max_per_minute=0, max_per_day=0)
    router = LLMRouter([_model("a", primary, blocked), _model("b", secondary)])

    result = await router.generate(_MSGS)

    assert result == "secondary"
    assert primary.calls == 0


async def test_falls_back_on_rate_limit_error() -> None:
    primary = FakeClient(errors=[RateLimitError("429")])
    secondary = FakeClient(text="secondary")
    router = LLMRouter([_model("a", primary), _model("b", secondary)])

    result = await router.generate(_MSGS)

    assert result == "secondary"
    assert primary.calls == 1


async def test_retries_transient_then_succeeds() -> None:
    slept: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        slept.append(seconds)

    primary = FakeClient(text="recovered", errors=[TransientLLMError("503")])
    router = LLMRouter([_model("a", primary)], max_retries=2, backoff_base=1.0, sleep=fake_sleep)

    result = await router.generate(_MSGS)

    assert result == "recovered"
    assert primary.calls == 2
    assert slept == [1.0]


async def test_transient_exhausts_retries_then_falls_back() -> None:
    async def fake_sleep(seconds: float) -> None:
        return None

    primary = FakeClient(errors=[TransientLLMError("503"), TransientLLMError("503")])
    secondary = FakeClient(text="secondary")
    router = LLMRouter(
        [_model("a", primary), _model("b", secondary)],
        max_retries=1,
        sleep=fake_sleep,
    )

    result = await router.generate(_MSGS)

    assert result == "secondary"
    assert primary.calls == 2


async def test_non_retryable_error_falls_back_without_retry() -> None:
    primary = FakeClient(errors=[LLMError("bad request")])
    secondary = FakeClient(text="secondary")
    router = LLMRouter([_model("a", primary), _model("b", secondary)])

    result = await router.generate(_MSGS)

    assert result == "secondary"
    assert primary.calls == 1


async def test_retries_on_rate_limit_then_succeeds() -> None:
    slept: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        slept.append(seconds)

    primary = FakeClient(text="recovered", errors=[RateLimitError("429"), RateLimitError("429")])
    model = RoutedModel(
        name="a",
        client=primary,
        limiter=_open_limiter(),
        rate_limit_retries=3,
        rate_limit_wait=20.0,
    )
    router = LLMRouter([model], sleep=fake_sleep)

    result = await router.generate(_MSGS)

    assert result == "recovered"
    assert primary.calls == 3
    assert slept == [20.0, 20.0]


async def test_rate_limit_retry_honors_retry_after_capped() -> None:
    slept: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        slept.append(seconds)

    primary = FakeClient(
        text="ok",
        errors=[RateLimitError("429", retry_after=5.0), RateLimitError("429", retry_after=999.0)],
    )
    model = RoutedModel(
        name="a",
        client=primary,
        limiter=_open_limiter(),
        rate_limit_retries=3,
        rate_limit_wait=20.0,
    )
    router = LLMRouter([model], sleep=fake_sleep)

    result = await router.generate(_MSGS)

    assert result == "ok"
    assert slept == [5.0, 60.0]  # retry_after 優先、ただし 60s で上限


async def test_rate_limit_exhausts_retries_then_falls_back() -> None:
    async def fake_sleep(seconds: float) -> None:
        return None

    primary = FakeClient(errors=[RateLimitError("429"), RateLimitError("429")])
    secondary = FakeClient(text="secondary")
    model = RoutedModel(
        name="a",
        client=primary,
        limiter=_open_limiter(),
        rate_limit_retries=1,
    )
    router = LLMRouter([model, _model("b", secondary)], sleep=fake_sleep)

    result = await router.generate(_MSGS)

    assert result == "secondary"
    assert primary.calls == 2


async def test_raises_when_all_models_fail() -> None:
    primary = FakeClient(errors=[RateLimitError("429")])
    secondary = FakeClient(errors=[LLMError("boom")])
    router = LLMRouter([_model("a", primary), _model("b", secondary)])

    with pytest.raises(LLMError):
        await router.generate(_MSGS)


def test_empty_chain_raises() -> None:
    with pytest.raises(ValueError, match="at least one model"):
        LLMRouter([])
