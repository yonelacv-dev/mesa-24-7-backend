"""Raíz de composición de waitlist: arma los casos de uso de la cola con sus adaptadores."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.database import get_session
from app.shared.application.ports import Clock, RealtimePublisher, TokenGenerator
from app.shared.dependencies import get_clock, get_publisher, get_stream_session_factory, get_tokens
from app.shared.infrastructure.unit_of_work import SQLAlchemyUnitOfWork
from app.venues.infrastructure.repository import SQLAlchemyVenueRepository
from app.waitlist.application.use_cases.change_entry_status import ChangeEntryStatusUseCase
from app.waitlist.application.use_cases.get_entry_state import GetEntryStateUseCase
from app.waitlist.application.use_cases.get_host_queue import GetHostQueueUseCase
from app.waitlist.application.use_cases.join_queue import JoinQueueUseCase
from app.waitlist.application.use_cases.leave_queue import LeaveQueueUseCase
from app.waitlist.application.use_cases.lookup_ticket import LookupTicketUseCase
from app.waitlist.application.use_cases.notify_on_the_way import NotifyOnTheWayUseCase
from app.waitlist.infrastructure.repositories import (
    SQLAlchemyEntryEventRepository,
    SQLAlchemyQueueEntryRepository,
    SQLAlchemyTicketCounter,
)


class WaitlistServices:
    """Los casos de uso de la cola sobre UNA sesión. Una por petición; los streams la abren por cada refresco."""

    def __init__(
        self, session: AsyncSession, clock: Clock, tokens: TokenGenerator, publisher: RealtimePublisher
    ) -> None:
        self._uow = SQLAlchemyUnitOfWork(session)
        self._venues = SQLAlchemyVenueRepository(session)
        self._entries = SQLAlchemyQueueEntryRepository(session)
        self._events = SQLAlchemyEntryEventRepository(session)
        self._tickets = SQLAlchemyTicketCounter(session)
        self._clock = clock
        self._tokens = tokens
        self._publisher = publisher

    @property
    def join_queue(self) -> JoinQueueUseCase:
        return JoinQueueUseCase(
            self._venues,
            self._entries,
            self._events,
            self._tickets,
            self._uow,
            self._clock,
            self._tokens,
            self._publisher,
        )

    @property
    def lookup_ticket(self) -> LookupTicketUseCase:
        return LookupTicketUseCase(self._venues, self._entries, self._clock)

    @property
    def get_entry_state(self) -> GetEntryStateUseCase:
        return GetEntryStateUseCase(self._venues, self._entries, self._clock)

    @property
    def leave_queue(self) -> LeaveQueueUseCase:
        return LeaveQueueUseCase(self._venues, self._entries, self._events, self._uow, self._clock, self._publisher)

    @property
    def notify_on_the_way(self) -> NotifyOnTheWayUseCase:
        return NotifyOnTheWayUseCase(self._venues, self._entries, self._events, self._uow, self._clock, self._publisher)

    @property
    def change_status(self) -> ChangeEntryStatusUseCase:
        return ChangeEntryStatusUseCase(self._entries, self._events, self._uow, self._clock, self._publisher)

    @property
    def host_queue(self) -> GetHostQueueUseCase:
        return GetHostQueueUseCase(self._venues, self._entries, self._clock)


def waitlist_services(
    session: AsyncSession = Depends(get_session),
    clock: Clock = Depends(get_clock),
    tokens: TokenGenerator = Depends(get_tokens),
    publisher: RealtimePublisher = Depends(get_publisher),
) -> WaitlistServices:
    return WaitlistServices(session, clock, tokens, publisher)


class WaitlistServicesFactory:
    """Abre una sesión corta por uso: los streams la piden en cada refresco en vez de retener una conexión."""

    def __init__(
        self,
        factory: async_sessionmaker[AsyncSession],
        clock: Clock,
        tokens: TokenGenerator,
        publisher: RealtimePublisher,
    ) -> None:
        self._factory = factory
        self._clock = clock
        self._tokens = tokens
        self._publisher = publisher

    @asynccontextmanager
    async def open(self) -> AsyncIterator[WaitlistServices]:
        async with self._factory() as session:
            yield WaitlistServices(session, self._clock, self._tokens, self._publisher)


def waitlist_services_factory(
    factory: async_sessionmaker[AsyncSession] = Depends(get_stream_session_factory),
    clock: Clock = Depends(get_clock),
    tokens: TokenGenerator = Depends(get_tokens),
    publisher: RealtimePublisher = Depends(get_publisher),
) -> WaitlistServicesFactory:
    return WaitlistServicesFactory(factory, clock, tokens, publisher)
