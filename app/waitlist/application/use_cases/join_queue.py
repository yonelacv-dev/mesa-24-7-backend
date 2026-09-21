from dataclasses import dataclass

from app.shared.application.errors import NotFound
from app.shared.application.ports import Clock, RealtimePublisher, TokenGenerator, UnitOfWork
from app.venues.application.ports import VenueRepository
from app.waitlist.application.errors import ActiveEntryAlreadyExists
from app.waitlist.application.ports import EntryEventRepository, QueueEntryRepository, TicketCounter
from app.waitlist.application.realtime import announce_entry_event
from app.waitlist.domain.entities import QueueEntry
from app.waitlist.domain.phone import normalize_phone

CONSENT_TEXT_VERSION = "v1"


@dataclass(frozen=True)
class JoinQueueCommand:
    venue_slug: str
    name: str
    phone: str
    party_size: int
    consent_accepted: bool


@dataclass(frozen=True)
class JoinResult:
    entry: QueueEntry
    already_in_queue: bool  # el teléfono ya tenía una entrada activa: se le devuelve esa, no se crea otra


class JoinQueueUseCase:
    def __init__(
        self,
        venues: VenueRepository,
        entries: QueueEntryRepository,
        events: EntryEventRepository,
        tickets: TicketCounter,
        uow: UnitOfWork,
        clock: Clock,
        tokens: TokenGenerator,
        publisher: RealtimePublisher,
    ):
        self._venues = venues
        self._entries = entries
        self._events = events
        self._tickets = tickets
        self._uow = uow
        self._clock = clock
        self._tokens = tokens
        self._publisher = publisher

    async def execute(self, cmd: JoinQueueCommand) -> JoinResult:
        venue = await self._venues.get_by_slug(cmd.venue_slug)
        if venue is None:
            raise NotFound("venue_not_found", "No encontramos ese local.")

        now = self._clock.now()
        venue.ensure_accepting(now)

        # Se valida todo antes de reservar un ticket para no quemar números por una petición inválida.
        QueueEntry.validate_join_data(cmd.name, cmd.party_size, cmd.consent_accepted)
        phone = normalize_phone(cmd.phone, venue.country_code)

        existing = await self._entries.get_active_by_phone(venue.id, phone)
        if existing is not None:
            return JoinResult(existing, already_in_queue=True)

        service_date = venue.service_date_at(now)
        ticket = await self._tickets.next_ticket(venue.id, service_date)
        entry = QueueEntry.join(
            venue_id=venue.id,
            public_token=self._tokens.new_token(),
            service_date=service_date,
            ticket=ticket,
            name=cmd.name,
            phone_e164=phone,
            party_size=cmd.party_size,
            consent_accepted=cmd.consent_accepted,
            consent_text_version=CONSENT_TEXT_VERSION,
            now=now,
        )
        try:
            await self._entries.add(entry)
        except ActiveEntryAlreadyExists:
            # Otro "Unirme" con el mismo teléfono ganó la carrera: se deshace el ticket y se devuelve esa entrada.
            await self._uow.rollback()
            existing = await self._entries.get_active_by_phone(venue.id, phone)
            return JoinResult(existing, already_in_queue=True)

        joined = await self._events.add(entry.joined_event())
        await self._uow.commit()
        await announce_entry_event(self._publisher, entry, joined)
        return JoinResult(entry, already_in_queue=False)
