from types import SimpleNamespace

import pytest

from app.shared.application.errors import NotFound
from app.venues.application.realtime import host_topic, venue_topic
from app.waitlist.domain.enums import Actor, EntryStatus, EventType
from app.waitlist.domain.errors import ActorNotAllowed, InvalidTransition

HOST = 10


async def act(world, entry, target, venue_id=1, user_id=HOST):
    return await world.change_status.execute(venue_id, user_id, entry.id, target)


async def test_call_starts_the_hold_and_records_who_did_it(world):
    entry = (await world.join()).entry
    world.clock.advance(minutes=2)

    await act(world, entry, EntryStatus.CALLED)

    assert entry.status is EntryStatus.CALLED and entry.called_at == world.clock.now()
    event = world.events.items[-1]
    assert (event.event_type, event.actor, event.user_id) == (EventType.CALLED, Actor.HOST, HOST)
    assert world.publisher.kinds(venue_topic(1))[-1] == "queue_changed"
    assert world.publisher.kinds(host_topic(1))[-1] == "called"


async def test_two_hosts_calling_the_same_row_apply_it_once(world):
    entry = (await world.join()).entry
    await act(world, entry, EntryStatus.CALLED, user_id=10)
    called_at, events = entry.called_at, len(world.events.items)
    world.clock.advance(minutes=1)

    await act(world, entry, EntryStatus.CALLED, user_id=11)

    assert entry.called_at == called_at  # el plazo no se reinicia
    assert len(world.events.items) == events


async def test_seat_requires_the_entry_to_be_called(world):
    entry = (await world.join()).entry
    with pytest.raises(InvalidTransition):
        await act(world, entry, EntryStatus.SEATED)

    await act(world, entry, EntryStatus.CALLED)
    await act(world, entry, EntryStatus.SEATED)

    assert entry.status is EntryStatus.SEATED and entry.ended_at is not None


async def test_no_show_only_applies_to_called_entries(world):
    entry = (await world.join()).entry
    with pytest.raises(InvalidTransition):
        await act(world, entry, EntryStatus.NO_SHOW)

    await act(world, entry, EntryStatus.CALLED)
    await act(world, entry, EntryStatus.NO_SHOW)

    assert entry.status is EntryStatus.NO_SHOW


@pytest.mark.parametrize("called_first", [False, True])
async def test_remove_works_whether_waiting_or_called(world, called_first):
    entry = (await world.join()).entry
    if called_first:
        await act(world, entry, EntryStatus.CALLED)

    await act(world, entry, EntryStatus.REMOVED)

    assert entry.status is EntryStatus.REMOVED
    assert world.events.items[-1].from_status is (EntryStatus.CALLED if called_first else EntryStatus.WAITING)


@pytest.mark.parametrize("target", [EntryStatus.CALLED, EntryStatus.SEATED, EntryStatus.NO_SHOW])
async def test_a_final_state_cannot_be_left(world, target):
    entry = (await world.join()).entry
    await act(world, entry, EntryStatus.REMOVED)

    with pytest.raises(InvalidTransition):
        await act(world, entry, target)
    assert entry.status is EntryStatus.REMOVED


async def test_repeating_a_final_action_is_a_noop(world):
    entry = (await world.join()).entry
    await act(world, entry, EntryStatus.REMOVED)
    events_before = len(world.events.items)

    await act(world, entry, EntryStatus.REMOVED)

    assert len(world.events.items) == events_before


async def test_host_cannot_cancel_on_behalf_of_the_diner(world):
    entry = (await world.join()).entry
    with pytest.raises(ActorNotAllowed):
        await act(world, entry, EntryStatus.CANCELLED)


async def test_host_cannot_touch_entries_of_another_venue(world):
    entry = (await world.join()).entry
    with pytest.raises(NotFound):
        await act(world, entry, EntryStatus.CALLED, venue_id=2)
    assert entry.status is EntryStatus.WAITING


async def test_unknown_entry_is_not_found(world):
    await world.join()
    with pytest.raises(NotFound):
        await act(world, SimpleNamespace(id=999), EntryStatus.CALLED)


async def test_full_history_is_recorded_in_order(world):
    entry = (await world.join()).entry
    await act(world, entry, EntryStatus.CALLED)
    await world.notify_on_the_way.execute(entry.public_token)
    await act(world, entry, EntryStatus.SEATED)

    assert [e.event_type for e in world.events.items] == [
        EventType.JOINED,
        EventType.CALLED,
        EventType.ON_THE_WAY,
        EventType.SEATED,
    ]
    assert [e.actor for e in world.events.items] == [Actor.DINER, Actor.HOST, Actor.DINER, Actor.HOST]


async def test_someone_who_did_not_show_can_join_again_and_goes_to_the_end(world):
    first, second = await world.join_many(2)
    await act(world, first.entry, EntryStatus.CALLED)
    await act(world, first.entry, EntryStatus.NO_SHOW)

    again = await world.join(phone="987654320")

    assert not again.already_in_queue and again.entry.ticket == 3
    assert (await world.get_entry_state.execute(again.entry.public_token)).position == 2
