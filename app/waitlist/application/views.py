from dataclasses import dataclass
from datetime import date, datetime

from app.venues.domain.entities import ListStatus, Venue
from app.waitlist.application.ports import QueueEntryRepository
from app.waitlist.domain.entities import QueueEntry
from app.waitlist.domain.enums import EntryStatus
from app.waitlist.domain.positioning import compute_positions, eta_range


@dataclass(frozen=True)
class EntryView:
    """Lo que ve el comensal de su propia entrada."""

    entry: QueueEntry
    venue: Venue
    position: int | None  # solo esperando
    eta: tuple[int, int] | None  # minutos, solo esperando
    hold_ends_at: datetime | None  # solo llamado
    server_time: datetime


@dataclass(frozen=True)
class HostEntryRow:
    entry: QueueEntry
    hold_ends_at: datetime | None
    hold_expired: bool


@dataclass(frozen=True)
class FinishedSummary:
    seated: int
    left: int  # cancelaron o fueron sacados
    no_show: int


@dataclass(frozen=True)
class HostQueueView:
    venue: Venue
    status: ListStatus
    rows: list[HostEntryRow]
    waiting: int
    called: int
    finished: FinishedSummary
    service_date: date | None
    server_time: datetime


async def build_entry_view(entries: QueueEntryRepository, venue: Venue, entry: QueueEntry, now: datetime) -> EntryView:
    position = eta = None
    if entry.status is EntryStatus.WAITING:
        position = compute_positions(await entries.list_active(venue.id)).get(entry.id)
        if position is not None:
            eta = eta_range(position, venue.minutes_per_position)
    return EntryView(
        entry=entry,
        venue=venue,
        position=position,
        eta=eta,
        hold_ends_at=entry.hold_ends_at(venue.hold_minutes),
        server_time=now,
    )
