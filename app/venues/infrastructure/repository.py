from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.venues.application.ports import VenueRepository
from app.venues.domain.entities import Venue
from app.venues.domain.schedule import DayWindow
from app.venues.infrastructure.models import VenueModel, VenueScheduleModel


def _to_domain(model: VenueModel) -> Venue:
    return Venue(
        id=model.id,
        slug=model.slug,
        name=model.name,
        country_code=model.country_code,
        timezone=model.timezone,
        minutes_per_position=model.minutes_per_position,
        hold_minutes=model.hold_minutes,
        paused=model.paused,
        schedule=tuple(DayWindow(row.is_open, row.start_time, row.end_time) for row in model.schedule),
    )


class SQLAlchemyVenueRepository(VenueRepository):
    def __init__(self, session: AsyncSession):
        self._session = session

    async def get_by_id(self, venue_id: int) -> Venue | None:
        model = await self._session.get(VenueModel, venue_id)
        return _to_domain(model) if model else None

    async def get_by_slug(self, slug: str) -> Venue | None:
        model = await self._session.scalar(select(VenueModel).where(VenueModel.slug == slug))
        return _to_domain(model) if model else None

    async def save(self, venue: Venue) -> None:
        model = await self._session.get(VenueModel, venue.id)
        model.name = venue.name
        model.minutes_per_position = venue.minutes_per_position
        model.hold_minutes = venue.hold_minutes
        model.paused = venue.paused

        rows = {row.weekday: row for row in model.schedule}
        for weekday, window in enumerate(venue.schedule):
            row = rows.get(weekday)
            if row is None:
                row = VenueScheduleModel(weekday=weekday)
                model.schedule.append(row)
            row.is_open, row.start_time, row.end_time = window.is_open, window.start, window.end
        await self._session.flush()
