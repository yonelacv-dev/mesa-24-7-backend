import math
from collections.abc import Iterable
from typing import Protocol

from app.waitlist.domain.enums import EntryStatus


class Queueable(Protocol):
    id: int | None
    status: EntryStatus

    @property
    def sort_key(self) -> tuple: ...


def compute_positions(entries: Iterable[Queueable]) -> dict[int, int]:
    """Posición = 1 + los que están esperando y llegaron antes. Los llamados no cuentan ni tienen posición."""
    waiting = sorted((e for e in entries if e.status is EntryStatus.WAITING), key=lambda e: e.sort_key)
    return {e.id: index + 1 for index, e in enumerate(waiting)}


def _round5(value: float) -> int:
    # round() de Python es bancario (12.5 -> 12); aquí queremos el redondeo comercial.
    return int(math.floor(value / 5 + 0.5)) * 5


def eta_range(position: int, minutes_per_position: int) -> tuple[int, int]:
    """Rango de espera en minutos, múltiplos de 5 y mínimo 5 a 10."""
    eta = position * minutes_per_position
    low = max(5, _round5(eta * 0.85))
    high = _round5(eta * 1.25)
    if high <= low:
        high = low + 5
    return low, high
