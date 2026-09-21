from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

from app.shared.domain.errors import ValidationFailed


@dataclass(frozen=True)
class DayWindow:
    """Ventana de un día de la semana en hora local del local. weekday: 0=lunes ... 6=domingo."""

    is_open: bool
    start: time
    end: time

    @property
    def crosses_midnight(self) -> bool:
        return self.end <= self.start


@dataclass(frozen=True)
class NextOpen:
    day_offset: int  # 0 = hoy, 1 = mañana, ...
    weekday: int
    time: time


@dataclass(frozen=True)
class ScheduleStatus:
    is_open: bool
    closes_at: time | None = None
    next_open: NextOpen | None = None  # None si el local no tiene ningún día abierto


def validate_schedule(windows: Sequence[DayWindow]) -> None:
    if len(windows) != 7:
        raise ValidationFailed("schedule_invalid", "El horario debe tener los 7 días de la semana.", field="schedule")
    for window in windows:
        if window.is_open and window.start == window.end:
            raise ValidationFailed(
                "schedule_start_equals_end",
                "La hora de inicio y la de cierre no pueden ser iguales.",
                field="schedule",
            )


def _naive(local_now: datetime) -> datetime:
    return local_now.replace(tzinfo=None)


def service_date_at(windows: Sequence[DayWindow], local_now: datetime) -> date | None:
    """Jornada de servicio: fecha de inicio de la ventana más reciente que ya empezó.

    Una ventana que cruza la medianoche pertenece al día en que empezó (00:30 del sábado es del viernes).
    """
    now = _naive(local_now)
    for days_back in range(8):
        day = now.date() - timedelta(days=days_back)
        window = windows[day.weekday()]
        if window.is_open and datetime.combine(day, window.start) <= now:
            return day
    return None


def evaluate_schedule(windows: Sequence[DayWindow], local_now: datetime) -> ScheduleStatus:
    now = _naive(local_now)
    today = now.date()
    t = now.time()
    weekday = today.weekday()

    # 1. ¿Sigue abierta la ventana de ayer que cruza la medianoche?
    yesterday = windows[(weekday - 1) % 7]
    if yesterday.is_open and yesterday.crosses_midnight and t < yesterday.end:
        return ScheduleStatus(is_open=True, closes_at=yesterday.end)

    # 2. Ventana de hoy.
    today_window = windows[weekday]
    if today_window.is_open:
        if today_window.crosses_midnight:
            if t >= today_window.start:
                return ScheduleStatus(is_open=True, closes_at=today_window.end)
        elif today_window.start <= t < today_window.end:
            return ScheduleStatus(is_open=True, closes_at=today_window.end)
        if t < today_window.start:
            return ScheduleStatus(is_open=False, next_open=NextOpen(0, weekday, today_window.start))

    # 3. Próximo día abierto. offset 7 es el mismo día de la semana siguiente.
    for offset in range(1, 8):
        index = (weekday + offset) % 7
        if windows[index].is_open:
            return ScheduleStatus(is_open=False, next_open=NextOpen(offset, index, windows[index].start))
    return ScheduleStatus(is_open=False)
