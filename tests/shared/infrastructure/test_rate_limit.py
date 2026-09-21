from app.shared.infrastructure.rate_limit import SlidingWindowRateLimiter


class Ticker:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def test_allows_up_to_the_limit_then_says_how_long_to_wait():
    ticker = Ticker()
    limiter = SlidingWindowRateLimiter(clock=ticker)

    results = [limiter.hit("k", 3, 60) for _ in range(4)]

    assert results == [None, None, None, 60]


def test_the_window_slides_so_old_attempts_stop_counting():
    ticker = Ticker()
    limiter = SlidingWindowRateLimiter(clock=ticker)
    for _ in range(3):
        limiter.hit("k", 3, 60)

    ticker.now += 30
    assert limiter.hit("k", 3, 60) == 30  # faltan 30 s para que salga el primer intento

    ticker.now += 31
    assert limiter.hit("k", 3, 60) is None


def test_keys_are_independent():
    limiter = SlidingWindowRateLimiter(clock=Ticker())
    for _ in range(3):
        limiter.hit("ip-a", 3, 60)

    assert limiter.hit("ip-a", 3, 60) is not None
    assert limiter.hit("ip-b", 3, 60) is None


def test_a_disabled_limiter_never_blocks():
    limiter = SlidingWindowRateLimiter(enabled=False, clock=Ticker())
    assert all(limiter.hit("k", 1, 60) is None for _ in range(50))


def test_retry_after_is_at_least_one_second():
    ticker = Ticker()
    limiter = SlidingWindowRateLimiter(clock=ticker)
    limiter.hit("k", 1, 60)
    ticker.now += 59.9

    assert limiter.hit("k", 1, 60) == 1
