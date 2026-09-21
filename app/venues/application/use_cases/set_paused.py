from app.shared.application.errors import NotFound
from app.shared.application.ports import Clock, RealtimeEvent, RealtimePublisher, UnitOfWork
from app.venues.application.ports import VenueRepository
from app.venues.application.realtime import QUEUE_CHANGED, host_topic, venue_topic
from app.venues.application.views import VenueStatusView


class SetPausedUseCase:
    def __init__(
        self,
        venues: VenueRepository,
        uow: UnitOfWork,
        clock: Clock,
        publisher: RealtimePublisher,
    ):
        self._venues = venues
        self._uow = uow
        self._clock = clock
        self._publisher = publisher

    async def execute(self, venue_id: int, paused: bool) -> VenueStatusView:
        venue = await self._venues.get_by_id(venue_id)
        if venue is None:
            raise NotFound("venue_not_found", "No encontramos ese local.")
        now = self._clock.now()
        if venue.paused != paused:
            venue.paused = paused
            await self._venues.save(venue)
            await self._uow.commit()
            await self._publisher.publish(venue_topic(venue.id), RealtimeEvent(QUEUE_CHANGED))
            await self._publisher.publish(host_topic(venue.id), RealtimeEvent("paused" if paused else "resumed"))
        return VenueStatusView(venue=venue, status=venue.status_at(now), server_time=now)
