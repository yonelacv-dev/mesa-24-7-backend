from datetime import time

from app.venues.application.views import VenueStatusView
from app.venues.domain.entities import ListStatus, Venue
from app.venues.presentation.schemas import (
    DayWindowOut,
    HostVenueOut,
    ListStatusOut,
    NextOpenOut,
    VenueOut,
    VenueStatusOut,
)


def hhmm(value: time) -> str:
    return value.strftime("%H:%M")


def list_status_out(status: ListStatus) -> ListStatusOut:
    next_open = status.next_open
    return ListStatusOut(
        kind=status.kind.value,
        closes_at=hhmm(status.closes_at) if status.closes_at else None,
        next_open=NextOpenOut(day_offset=next_open.day_offset, weekday=next_open.weekday, time=hhmm(next_open.time))
        if next_open
        else None,
    )


def venue_out(venue: Venue) -> VenueOut:
    return VenueOut(slug=venue.slug, name=venue.name, country_code=venue.country_code, phone_prefix=venue.phone_prefix)


def venue_status_out(view: VenueStatusView) -> VenueStatusOut:
    return VenueStatusOut(
        venue=venue_out(view.venue), status=list_status_out(view.status), server_time=view.server_time
    )


def host_venue_out(venue: Venue, status: ListStatus) -> HostVenueOut:
    return HostVenueOut(
        slug=venue.slug,
        name=venue.name,
        country_code=venue.country_code,
        phone_prefix=venue.phone_prefix,
        timezone=venue.timezone,
        paused=venue.paused,
        hold_minutes=venue.hold_minutes,
        minutes_per_position=venue.minutes_per_position,
        list_status=list_status_out(status),
        schedule=[
            DayWindowOut(
                weekday=weekday,
                is_open=window.is_open,
                start=hhmm(window.start),
                end=hhmm(window.end),
                crosses_midnight=window.is_open and window.crosses_midnight,
            )
            for weekday, window in enumerate(venue.schedule)
        ],
    )
