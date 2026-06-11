"""SlidingRateLimiter のテスト（注入クロックで時間を制御）。"""

from thesis_ai.llm.router import SlidingRateLimiter


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


def test_allows_up_to_per_minute_limit() -> None:
    clock = FakeClock()
    limiter = SlidingRateLimiter(max_per_minute=2, max_per_day=100, clock=clock)

    assert limiter.allow() is True
    assert limiter.allow() is True
    assert limiter.allow() is False


def test_minute_window_slides() -> None:
    clock = FakeClock()
    limiter = SlidingRateLimiter(max_per_minute=1, max_per_day=100, clock=clock)

    assert limiter.allow() is True
    assert limiter.allow() is False

    clock.now = 60.0  # 1 分経過で枠が空く
    assert limiter.allow() is True


def test_daily_limit_blocks_within_minute_budget() -> None:
    clock = FakeClock()
    limiter = SlidingRateLimiter(max_per_minute=100, max_per_day=2, clock=clock)

    assert limiter.allow() is True
    clock.now += 1
    assert limiter.allow() is True
    clock.now += 1
    assert limiter.allow() is False


def test_daily_window_slides() -> None:
    clock = FakeClock()
    limiter = SlidingRateLimiter(max_per_minute=100, max_per_day=1, clock=clock)

    assert limiter.allow() is True
    clock.now = 86_400.0  # 1 日経過
    assert limiter.allow() is True
