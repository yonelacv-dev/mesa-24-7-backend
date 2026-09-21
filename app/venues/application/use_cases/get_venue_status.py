from app.shared.application.errors import NotFound
from app.shared.application.ports import Clock
from app.venues.application.ports import VenueRepository
from app.venues.application.views import VenueStatusView


class GetVenueStatusUseCase:
    def __init__(self, venues: VenueRepository, clock: Clock):
        self._venues = venues
        self._clock = clock

    async def execute(self, slug: str) -> VenueStatusView:
        venue = await self._venues.get_by_slug(slug)
        if venue is None:
            raise NotFound("venue_not_found", "No encontramos ese local.")
        now = self._clock.now()
        return VenueStatusView(venue=venue, status=venue.status_at(now), server_time=now)
