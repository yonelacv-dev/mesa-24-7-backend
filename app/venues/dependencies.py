"""Raíz de composición de venues + el contexto del anfitrión (usuario autenticado que pertenece al local)."""

from dataclasses import dataclass

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.application.views import AuthenticatedUser
from app.auth.dependencies import current_user
from app.database import get_session
from app.shared.application.errors import Forbidden
from app.shared.application.ports import Clock, RealtimePublisher, UnitOfWork
from app.shared.dependencies import get_clock, get_publisher, get_uow
from app.venues.application.use_cases.get_venue import GetVenueUseCase
from app.venues.application.use_cases.get_venue_status import GetVenueStatusUseCase
from app.venues.application.use_cases.set_paused import SetPausedUseCase
from app.venues.application.use_cases.update_schedule import UpdateScheduleUseCase
from app.venues.infrastructure.repository import SQLAlchemyVenueRepository


class VenueServices:
    def __init__(self, session: AsyncSession, uow: UnitOfWork, clock: Clock, publisher: RealtimePublisher):
        self.repository = SQLAlchemyVenueRepository(session)
        self._uow = uow
        self._clock = clock
        self._publisher = publisher

    @property
    def get_venue(self) -> GetVenueUseCase:
        return GetVenueUseCase(self.repository)

    @property
    def get_status(self) -> GetVenueStatusUseCase:
        return GetVenueStatusUseCase(self.repository, self._clock)

    @property
    def set_paused(self) -> SetPausedUseCase:
        return SetPausedUseCase(self.repository, self._uow, self._clock, self._publisher)

    @property
    def update_schedule(self) -> UpdateScheduleUseCase:
        return UpdateScheduleUseCase(self.repository, self._uow, self._clock, self._publisher)


def venue_services(
    session: AsyncSession = Depends(get_session),
    uow: UnitOfWork = Depends(get_uow),
    clock: Clock = Depends(get_clock),
    publisher: RealtimePublisher = Depends(get_publisher),
) -> VenueServices:
    return VenueServices(session, uow, clock, publisher)


@dataclass(frozen=True)
class HostContext:
    user: AuthenticatedUser
    venue_id: int
    slug: str


async def host_context(
    slug: str,
    user: AuthenticatedUser = Depends(current_user),
    services: VenueServices = Depends(venue_services),
) -> HostContext:
    """El anfitrión solo opera sobre el local de su cuenta: la ruta y el token tienen que coincidir."""
    venue = await services.repository.get_by_slug(slug)
    if venue is None or venue.id != user.venue_id:
        raise Forbidden("venue_forbidden", "Esta cuenta no puede operar en este local.")
    return HostContext(user=user, venue_id=venue.id, slug=venue.slug)
