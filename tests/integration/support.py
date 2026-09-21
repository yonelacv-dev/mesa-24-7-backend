from contextlib import asynccontextmanager
from datetime import time

from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from app.auth.application.use_cases.authenticate import AuthenticateUseCase
from app.auth.application.use_cases.login import LoginUseCase
from app.auth.application.use_cases.logout import LogoutUseCase
from app.auth.domain.entities import User
from app.auth.infrastructure.argon2_hasher import Argon2PasswordHasher
from app.auth.infrastructure.models import UserModel
from app.auth.infrastructure.repositories import SQLAlchemyAuthSessionRepository, SQLAlchemyUserRepository
from app.shared.infrastructure.realtime import InMemoryRealtimeBroker
from app.shared.infrastructure.tokens import SecretsTokenGenerator
from app.shared.infrastructure.unit_of_work import SQLAlchemyUnitOfWork
from app.venues.application.use_cases.set_paused import SetPausedUseCase
from app.venues.application.use_cases.update_schedule import UpdateScheduleUseCase
from app.venues.domain.entities import Venue
from app.venues.infrastructure.models import VenueModel, VenueScheduleModel
from app.venues.infrastructure.repository import SQLAlchemyVenueRepository
from app.waitlist.application.use_cases.change_entry_status import ChangeEntryStatusUseCase
from app.waitlist.application.use_cases.get_entry_state import GetEntryStateUseCase
from app.waitlist.application.use_cases.get_host_queue import GetHostQueueUseCase
from app.waitlist.application.use_cases.join_queue import JoinQueueCommand, JoinQueueUseCase, JoinResult
from app.waitlist.application.use_cases.leave_queue import LeaveQueueUseCase
from app.waitlist.application.use_cases.lookup_ticket import LookupTicketCommand, LookupTicketUseCase
from app.waitlist.application.use_cases.notify_on_the_way import NotifyOnTheWayUseCase
from app.waitlist.infrastructure.repositories import (
    SQLAlchemyEntryEventRepository,
    SQLAlchemyQueueEntryRepository,
    SQLAlchemyTicketCounter,
)
from tests.support.fakes import FakeClock
from tests.support.world import FRIDAY_2000_LIMA

HASHER = Argon2PasswordHasher()  # costoso de crear: uno para toda la suite


class Wired:
    """Los casos de uso armados con adaptadores reales sobre UNA sesión, como en una petición HTTP."""

    def __init__(self, session, clock: FakeClock, broker: InMemoryRealtimeBroker):
        self.session = session
        self.clock = clock
        self.broker = broker
        self.uow = SQLAlchemyUnitOfWork(session)
        self.venues = SQLAlchemyVenueRepository(session)
        self.entries = SQLAlchemyQueueEntryRepository(session)
        self.events = SQLAlchemyEntryEventRepository(session)
        self.tickets = SQLAlchemyTicketCounter(session)
        self.users = SQLAlchemyUserRepository(session)
        self.auth_sessions = SQLAlchemyAuthSessionRepository(session)
        self.tokens = SecretsTokenGenerator()

    @property
    def join_queue(self):
        return JoinQueueUseCase(
            self.venues, self.entries, self.events, self.tickets, self.uow, self.clock, self.tokens, self.broker
        )

    @property
    def lookup_ticket(self):
        return LookupTicketUseCase(self.venues, self.entries, self.clock)

    @property
    def get_entry_state(self):
        return GetEntryStateUseCase(self.venues, self.entries, self.clock)

    @property
    def leave_queue(self):
        return LeaveQueueUseCase(self.venues, self.entries, self.events, self.uow, self.clock, self.broker)

    @property
    def notify_on_the_way(self):
        return NotifyOnTheWayUseCase(self.venues, self.entries, self.events, self.uow, self.clock, self.broker)

    @property
    def change_status(self):
        return ChangeEntryStatusUseCase(self.entries, self.events, self.uow, self.clock, self.broker)

    @property
    def host_queue(self):
        return GetHostQueueUseCase(self.venues, self.entries, self.clock)

    @property
    def set_paused(self):
        return SetPausedUseCase(self.venues, self.uow, self.clock, self.broker)

    @property
    def update_schedule(self):
        return UpdateScheduleUseCase(self.venues, self.uow, self.clock, self.broker)

    @property
    def login(self):
        return LoginUseCase(self.users, self.auth_sessions, HASHER, self.tokens, self.uow, self.clock)

    @property
    def authenticate(self):
        return AuthenticateUseCase(self.users, self.auth_sessions, self.uow, self.clock)

    @property
    def logout(self):
        return LogoutUseCase(self.auth_sessions, self.uow, self.clock)

    async def join(self, slug: str, phone: str = "987654321", name: str = "Carla", party_size: int = 2) -> JoinResult:
        return await self.join_queue.execute(JoinQueueCommand(slug, name, phone, party_size, True))

    async def lookup(self, slug: str, ticket: int, phone: str):
        return await self.lookup_ticket.execute(LookupTicketCommand(slug, ticket, phone))


class Db:
    def __init__(self, engine: AsyncEngine):
        self.engine = engine
        self.factory = async_sessionmaker(engine, expire_on_commit=False)
        self.clock = FakeClock(FRIDAY_2000_LIMA)
        self.broker = InMemoryRealtimeBroker()

    @asynccontextmanager
    async def scope(self):
        """Una 'petición': sesión propia, casos de uso propios."""
        async with self.factory() as session:
            yield Wired(session, self.clock, self.broker)

    async def create_venue(
        self,
        slug: str = "la-terraza-azul",
        name: str = "La Terraza Azul",
        country: str = "PE",
        timezone: str = "America/Lima",
    ) -> Venue:
        async with self.factory() as session:
            model = VenueModel(slug=slug, name=name, country_code=country, timezone=timezone)
            model.schedule = [
                VenueScheduleModel(weekday=day, is_open=True, start_time=time(11, 0), end_time=time(1, 0))
                for day in range(7)
            ]
            session.add(model)
            await session.commit()
            venue_id = model.id
        async with self.factory() as session:  # sesión nueva: las columnas con default del servidor se releen
            return await SQLAlchemyVenueRepository(session).get_by_id(venue_id)

    async def create_user(self, venue_id: int, username: str = "terraza", password: str = "secreto") -> User:
        async with self.factory() as session:
            model = UserModel(venue_id=venue_id, username=username, password_hash=await HASHER.hash(password))
            session.add(model)
            await session.commit()
            return User(id=model.id, venue_id=venue_id, username=username, password_hash=model.password_hash)
