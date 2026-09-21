from dataclasses import dataclass
from datetime import datetime

from app.venues.domain.entities import ListStatus, Venue


@dataclass(frozen=True)
class VenueStatusView:
    venue: Venue
    status: ListStatus
    server_time: datetime
