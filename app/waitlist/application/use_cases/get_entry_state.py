from app.shared.application.errors import NotFound
from app.shared.application.ports import Clock
from app.venues.application.ports import VenueRepository
from app.waitlist.application.ports import QueueEntryRepository
from app.waitlist.application.views import EntryView, build_entry_view


class GetEntryStateUseCase:
    def __init__(self, venues: VenueRepository, entries: QueueEntryRepository, clock: Clock):
        self._venues = venues
        self._entries = entries
        self._clock = clock

    async def execute(self, token: str, venue_slug: str | None = None) -> EntryView:
        """`venue_slug`: si viene, el token solo vale en ese local (la ruta lo lleva)."""
        entry = await self._entries.get_by_token(token)
        if entry is None:
            raise NotFound("entry_not_found", "No encontramos tu turno.")
        venue = await self._venues.get_by_id(entry.venue_id)
        if venue_slug is not None and venue.slug != venue_slug:
            raise NotFound("entry_not_found", "No encontramos tu turno.")
        return await build_entry_view(self._entries, venue, entry, self._clock.now())
