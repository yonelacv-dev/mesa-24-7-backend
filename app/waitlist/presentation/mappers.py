from app.venues.presentation.mappers import host_venue_out
from app.waitlist.application.views import EntryView, HostQueueView
from app.waitlist.domain.phone import display_phone
from app.waitlist.presentation.schemas import (
    EntryOut,
    EntryVenueOut,
    EtaOut,
    FinishedOut,
    HostQueueOut,
    HostRowOut,
)


def entry_out(view: EntryView) -> EntryOut:
    entry = view.entry
    return EntryOut(
        token=entry.public_token,
        ticket=entry.ticket,
        name=entry.name,
        party_size=entry.party_size,
        phone_display=display_phone(entry.phone_e164),
        status=entry.status.value,
        position=view.position,
        eta=EtaOut(min=view.eta[0], max=view.eta[1]) if view.eta else None,
        hold_ends_at=view.hold_ends_at,
        on_the_way=entry.on_the_way_at is not None,
        venue=EntryVenueOut(slug=view.venue.slug, name=view.venue.name),
        server_time=view.server_time,
    )


def host_queue_out(view: HostQueueView) -> HostQueueOut:
    return HostQueueOut(
        venue=host_venue_out(view.venue, view.status),
        waiting=view.waiting,
        called=view.called,
        rows=[
            HostRowOut(
                id=row.entry.id,
                ticket=row.entry.ticket,
                name=row.entry.name,
                party_size=row.entry.party_size,
                phone_e164=row.entry.phone_e164,
                phone_display=display_phone(row.entry.phone_e164),
                status=row.entry.status.value,
                joined_at=row.entry.joined_at,
                called_at=row.entry.called_at,
                hold_ends_at=row.hold_ends_at,
                hold_expired=row.hold_expired,
                on_the_way=row.entry.on_the_way_at is not None,
            )
            for row in view.rows
        ],
        finished=FinishedOut(seated=view.finished.seated, left=view.finished.left, no_show=view.finished.no_show),
        service_date=view.service_date,
        server_time=view.server_time,
    )
