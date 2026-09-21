from dataclasses import dataclass

from app.shared.application.errors import NotFound
from app.shared.application.ports import Clock
from app.shared.domain.errors import ValidationFailed
from app.venues.application.ports import VenueRepository
from app.waitlist.application.ports import QueueEntryRepository
from app.waitlist.application.views import EntryView, build_entry_view
from app.waitlist.domain.phone import normalize_phone


@dataclass(frozen=True)
class LookupTicketCommand:
    venue_slug: str
    ticket: int
    phone: str


class LookupTicketUseCase:
    """Recupera el turno con número de ticket Y teléfono, para que nadie pueda probar números y ver turnos ajenos."""

    def __init__(self, venues: VenueRepository, entries: QueueEntryRepository, clock: Clock):
        self._venues = venues
        self._entries = entries
        self._clock = clock

    async def execute(self, cmd: LookupTicketCommand) -> EntryView:
        venue = await self._venues.get_by_slug(cmd.venue_slug)
        if venue is None:
            raise NotFound("venue_not_found", "No encontramos ese local.")

        # Un teléfono inválido y un ticket inexistente responden igual: no se filtra qué dato falló.
        not_found = NotFound(
            "ticket_not_found", "No encontramos un ticket con esos datos. Revisa el número y el teléfono."
        )
        try:
            phone = normalize_phone(cmd.phone, venue.country_code)
        except ValidationFailed:
            raise not_found from None

        entry = await self._entries.find_for_lookup(venue.id, cmd.ticket, phone)
        if entry is None:
            raise not_found
        return await build_entry_view(self._entries, venue, entry, self._clock.now())
