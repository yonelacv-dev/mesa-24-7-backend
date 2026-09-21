from app.shared.application.errors import NotFound
from app.shared.application.ports import Clock
from app.venues.application.ports import VenueRepository
from app.waitlist.application.ports import QueueEntryRepository
from app.waitlist.application.views import FinishedSummary, HostEntryRow, HostQueueView
from app.waitlist.domain.enums import EntryStatus


class GetHostQueueUseCase:
    def __init__(self, venues: VenueRepository, entries: QueueEntryRepository, clock: Clock):
        self._venues = venues
        self._entries = entries
        self._clock = clock

    async def execute(self, venue_id: int) -> HostQueueView:
        venue = await self._venues.get_by_id(venue_id)
        if venue is None:
            raise NotFound("venue_not_found", "No encontramos ese local.")
        now = self._clock.now()

        active = await self._entries.list_active(venue.id)
        rows = [
            HostEntryRow(
                entry=entry,
                hold_ends_at=entry.hold_ends_at(venue.hold_minutes),
                hold_expired=entry.is_hold_expired(now, venue.hold_minutes),
            )
            for entry in sorted(active, key=lambda e: e.sort_key)
        ]
        waiting = sum(1 for row in rows if row.entry.status is EntryStatus.WAITING)

        service_date = venue.service_date_at(now)
        counts = await self._entries.count_by_status(venue.id, service_date) if service_date else {}
        finished = FinishedSummary(
            seated=counts.get(EntryStatus.SEATED, 0),
            left=counts.get(EntryStatus.CANCELLED, 0) + counts.get(EntryStatus.REMOVED, 0),
            no_show=counts.get(EntryStatus.NO_SHOW, 0),
        )
        return HostQueueView(
            venue=venue,
            status=venue.status_at(now),
            rows=rows,
            waiting=waiting,
            called=len(rows) - waiting,
            finished=finished,
            service_date=service_date,
            server_time=now,
        )
