from app.shared.application.errors import NotFound
from app.shared.application.ports import Clock, RealtimePublisher, UnitOfWork
from app.venues.application.ports import VenueRepository
from app.waitlist.application.ports import EntryEventRepository, QueueEntryRepository
from app.waitlist.application.realtime import announce_entry_event
from app.waitlist.application.views import EntryView, build_entry_view
from app.waitlist.domain.enums import Actor, EntryStatus


class LeaveQueueUseCase:
    """'Ya no voy': el comensal sale de la cola. Antes o después de ser llamado siempre cuenta como Canceló."""

    def __init__(
        self,
        venues: VenueRepository,
        entries: QueueEntryRepository,
        events: EntryEventRepository,
        uow: UnitOfWork,
        clock: Clock,
        publisher: RealtimePublisher,
    ):
        self._venues = venues
        self._entries = entries
        self._events = events
        self._uow = uow
        self._clock = clock
        self._publisher = publisher

    async def execute(self, token: str, venue_slug: str | None = None) -> EntryView:
        entry = await self._entries.get_by_token_for_update(token)
        if entry is None:
            raise NotFound("entry_not_found", "No encontramos tu turno.")
        venue = await self._venues.get_by_id(entry.venue_id)
        if venue_slug is not None and venue.slug != venue_slug:
            raise NotFound("entry_not_found", "No encontramos tu turno.")
        now = self._clock.now()

        event = entry.transition(EntryStatus.CANCELLED, Actor.DINER, now)
        if event is not None:
            await self._entries.save(entry)
            event = await self._events.add(event)
        await self._uow.commit()
        if event is not None:
            await announce_entry_event(self._publisher, entry, event)

        return await build_entry_view(self._entries, venue, entry, now)
