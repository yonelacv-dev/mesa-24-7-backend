from dataclasses import dataclass
from datetime import date, datetime, time
from zoneinfo import ZoneInfo

import phonenumbers

from app.venues.domain.enums import ListStatusKind
from app.venues.domain.errors import ListClosed, ListPaused
from app.venues.domain.schedule import DayWindow, NextOpen, evaluate_schedule, service_date_at

DEFAULT_MINUTES_PER_POSITION = 4
DEFAULT_HOLD_MINUTES = 10


@dataclass(frozen=True)
class ListStatus:
    kind: ListStatusKind
    closes_at: time | None = None
    next_open: NextOpen | None = None


@dataclass
class Venue:
    slug: str
    name: str
    country_code: str
    timezone: str
    id: int | None = None
    minutes_per_position: int = DEFAULT_MINUTES_PER_POSITION
    hold_minutes: int = DEFAULT_HOLD_MINUTES
    paused: bool = False
    schedule: tuple[DayWindow, ...] = ()

    def local_now(self, now_utc: datetime) -> datetime:
        return now_utc.astimezone(ZoneInfo(self.timezone))

    def status_at(self, now_utc: datetime) -> ListStatus:
        """Cerrada si está fuera de horario (aunque esté en pausa); en pausa solo si está dentro de horario."""
        schedule_status = evaluate_schedule(self.schedule, self.local_now(now_utc))
        if not schedule_status.is_open:
            return ListStatus(ListStatusKind.CLOSED, next_open=schedule_status.next_open)
        if self.paused:
            return ListStatus(ListStatusKind.PAUSED, closes_at=schedule_status.closes_at)
        return ListStatus(ListStatusKind.OPEN, closes_at=schedule_status.closes_at)

    def service_date_at(self, now_utc: datetime) -> date | None:
        return service_date_at(self.schedule, self.local_now(now_utc))

    def ensure_accepting(self, now_utc: datetime) -> ListStatus:
        """Nadie puede unirse fuera de horario ni con la lista en pausa."""
        status = self.status_at(now_utc)
        if status.kind is ListStatusKind.CLOSED:
            raise ListClosed("list_closed", "La lista de espera está cerrada.")
        if status.kind is ListStatusKind.PAUSED:
            raise ListPaused("list_paused", "La lista está en pausa.")
        return status

    @property
    def phone_prefix(self) -> str:
        return f"+{phonenumbers.country_code_for_region(self.country_code)}"
