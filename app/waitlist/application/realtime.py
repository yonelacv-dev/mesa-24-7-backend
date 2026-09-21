from app.shared.application.ports import RealtimeEvent, RealtimePublisher
from app.venues.application.realtime import QUEUE_CHANGED, host_topic, venue_topic
from app.waitlist.domain.entities import EntryEvent, QueueEntry
from app.waitlist.domain.phone import display_phone


async def announce_entry_event(publisher: RealtimePublisher, entry: QueueEntry, event: EntryEvent) -> None:
    """Avisa a todos que la cola cambió y al anfitrión, además, qué pasó exactamente."""
    await publisher.publish(venue_topic(entry.venue_id), RealtimeEvent(QUEUE_CHANGED))
    await publisher.publish(
        host_topic(entry.venue_id),
        RealtimeEvent(
            event.event_type.value,
            {
                "entry_id": entry.id,
                "ticket": entry.ticket,
                "name": entry.name,
                "party_size": entry.party_size,
                "phone_e164": entry.phone_e164,
                "phone_display": display_phone(entry.phone_e164),
            },
        ),
    )
