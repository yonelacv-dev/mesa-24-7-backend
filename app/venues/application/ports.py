from abc import ABC, abstractmethod

from app.venues.domain.entities import Venue


class VenueRepository(ABC):
    @abstractmethod
    async def get_by_id(self, venue_id: int) -> Venue | None: ...

    @abstractmethod
    async def get_by_slug(self, slug: str) -> Venue | None: ...

    @abstractmethod
    async def save(self, venue: Venue) -> None:
        """Persiste los cambios del local, incluido su horario semanal."""
