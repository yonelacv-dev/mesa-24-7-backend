import math
import time
from collections import deque
from collections.abc import Callable

from app.shared.application.ports import RateLimiter

PURGE_THRESHOLD = 10_000


class SlidingWindowRateLimiter(RateLimiter):
    """Ventana deslizante en memoria del proceso: suficiente para un solo worker (el piloto)."""

    def __init__(self, enabled: bool = True, clock: Callable[[], float] = time.monotonic):
        self._enabled = enabled
        self._clock = clock
        self._hits: dict[str, deque[float]] = {}

    def hit(self, key: str, limit: int, window_seconds: float) -> int | None:
        """Registra un intento. Devuelve None si pasa, o los segundos que faltan para poder reintentar."""
        if not self._enabled:
            return None
        now = self._clock()
        if len(self._hits) > PURGE_THRESHOLD:
            self._purge(now, window_seconds)
        hits = self._hits.setdefault(key, deque())
        while hits and hits[0] <= now - window_seconds:
            hits.popleft()
        if len(hits) >= limit:
            return max(1, math.ceil(hits[0] + window_seconds - now))
        hits.append(now)
        return None

    def _purge(self, now: float, window_seconds: float) -> None:
        for key in [k for k, hits in self._hits.items() if not hits or hits[-1] <= now - window_seconds]:
            del self._hits[key]
