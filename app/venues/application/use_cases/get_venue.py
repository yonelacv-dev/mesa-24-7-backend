from app.shared.application.errors import NotFound
from app.venues.application.ports import VenueRepository
from app.venues.domain.entities import Venue


class GetVenueUseCase:
    def __init__(self, venues: VenueRepository):
        self._venues = venues

    async def execute(self, venue_id: int) -> Venue:
        venue = await self._venues.get_by_id(venue_id)
        if venue is None:
            raise NotFound("venue_not_found", "No encontramos ese local.")
        return venue
