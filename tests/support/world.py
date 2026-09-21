from datetime import UTC, datetime, time

from app.auth.application.use_cases.authenticate import AuthenticateUseCase
from app.auth.application.use_cases.login import LoginUseCase
from app.auth.application.use_cases.logout import LogoutUseCase
from app.auth.domain.entities import User
from app.venues.application.use_cases.get_venue_status import GetVenueStatusUseCase
from app.venues.application.use_cases.set_paused import SetPausedUseCase
from app.venues.application.use_cases.update_schedule import UpdateScheduleUseCase
from app.venues.domain.entities import Venue
from app.venues.domain.schedule import DayWindow
from app.waitlist.application.use_cases.change_entry_status import ChangeEntryStatusUseCase
from app.waitlist.application.use_cases.get_entry_state import GetEntryStateUseCase
from app.waitlist.application.use_cases.get_host_queue import GetHostQueueUseCase
from app.waitlist.application.use_cases.join_queue import JoinQueueCommand, JoinQueueUseCase, JoinResult
from app.waitlist.application.use_cases.leave_queue import LeaveQueueUseCase
from app.waitlist.application.use_cases.lookup_ticket import LookupTicketCommand, LookupTicketUseCase
from app.waitlist.application.use_cases.notify_on_the_way import NotifyOnTheWayUseCase
from tests.support.fakes import (
    FakeClock,
    FakeHasher,
    FakeUnitOfWork,
    InMemoryEntries,
    InMemoryEvents,
    InMemorySessions,
    InMemoryTickets,
    InMemoryUsers,
    InMemoryVenues,
    RecordingPublisher,
    SequentialTokens,
)

# Viernes 2026-09-18 20:00 en Lima (UTC-5): dentro del horario 11:00 a 01:00.
FRIDAY_2000_LIMA = datetime(2026, 9, 19, 1, 0, tzinfo=UTC)

SLUG = "la-terraza-azul"
OTHER_SLUG = "cuatro-vientos"
LATE_NIGHT = DayWindow(True, time(11, 0), time(1, 0))


class World:
    """Arma los casos de uso con adaptadores en memoria para probar la capa application."""

    def __init__(self) -> None:
        self.clock = FakeClock(FRIDAY_2000_LIMA)
        self.uow = FakeUnitOfWork()
        self.publisher = RecordingPublisher()
        self.tokens = SequentialTokens()
        self.hasher = FakeHasher()
        self.venues = InMemoryVenues()
        self.entries = InMemoryEntries()
        self.events = InMemoryEvents()
        self.tickets = InMemoryTickets()
        self.users = InMemoryUsers()
        self.sessions = InMemorySessions()

        week = (LATE_NIGHT,) * 7
        self.venue = self.venues.add(
            Venue(id=1, slug=SLUG, name="La Terraza Azul", country_code="PE", timezone="America/Lima", schedule=week)
        )
        self.other_venue = self.venues.add(
            Venue(
                id=2, slug=OTHER_SLUG, name="Cuatro Vientos", country_code="PE", timezone="America/Lima", schedule=week
            )
        )
        self.user = self.users.add(User(id=10, venue_id=1, username="terraza", password_hash="hashed:secreto"))

    # --- casos de uso -----------------------------------------------------------------------------
    @property
    def join_queue(self) -> JoinQueueUseCase:
        return JoinQueueUseCase(
            self.venues, self.entries, self.events, self.tickets, self.uow, self.clock, self.tokens, self.publisher
        )

    @property
    def lookup_ticket(self) -> LookupTicketUseCase:
        return LookupTicketUseCase(self.venues, self.entries, self.clock)

    @property
    def get_entry_state(self) -> GetEntryStateUseCase:
        return GetEntryStateUseCase(self.venues, self.entries, self.clock)

    @property
    def leave_queue(self) -> LeaveQueueUseCase:
        return LeaveQueueUseCase(self.venues, self.entries, self.events, self.uow, self.clock, self.publisher)

    @property
    def notify_on_the_way(self) -> NotifyOnTheWayUseCase:
        return NotifyOnTheWayUseCase(self.venues, self.entries, self.events, self.uow, self.clock, self.publisher)

    @property
    def change_status(self) -> ChangeEntryStatusUseCase:
        return ChangeEntryStatusUseCase(self.entries, self.events, self.uow, self.clock, self.publisher)

    @property
    def host_queue(self) -> GetHostQueueUseCase:
        return GetHostQueueUseCase(self.venues, self.entries, self.clock)

    @property
    def venue_status(self) -> GetVenueStatusUseCase:
        return GetVenueStatusUseCase(self.venues, self.clock)

    @property
    def set_paused(self) -> SetPausedUseCase:
        return SetPausedUseCase(self.venues, self.uow, self.clock, self.publisher)

    @property
    def update_schedule(self) -> UpdateScheduleUseCase:
        return UpdateScheduleUseCase(self.venues, self.uow, self.clock, self.publisher)

    @property
    def login(self) -> LoginUseCase:
        return LoginUseCase(self.users, self.sessions, self.hasher, self.tokens, self.uow, self.clock)

    @property
    def authenticate(self) -> AuthenticateUseCase:
        return AuthenticateUseCase(self.users, self.sessions, self.uow, self.clock)

    @property
    def logout(self) -> LogoutUseCase:
        return LogoutUseCase(self.sessions, self.uow, self.clock)

    # --- atajos -------------------------------------------------------------------------------------
    async def join(
        self,
        name: str = "Carla",
        phone: str = "987654321",
        party_size: int = 2,
        slug: str = SLUG,
        consent: bool = True,
    ) -> JoinResult:
        return await self.join_queue.execute(JoinQueueCommand(slug, name, phone, party_size, consent))

    async def join_many(self, count: int, slug: str = SLUG) -> list[JoinResult]:
        results = []
        for i in range(count):
            results.append(await self.join(name=f"Comensal {i + 1}", phone=f"98765432{i}", slug=slug))
            self.clock.advance(minutes=1)
        return results

    async def lookup(self, ticket: int, phone: str, slug: str = SLUG):
        return await self.lookup_ticket.execute(LookupTicketCommand(slug, ticket, phone))
