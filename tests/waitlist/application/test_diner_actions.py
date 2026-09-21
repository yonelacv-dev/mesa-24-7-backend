import pytest

from app.shared.application.errors import NotFound
from app.venues.application.realtime import host_topic
from app.waitlist.domain.enums import Actor, EntryStatus, EventType
from app.waitlist.domain.errors import InvalidTransition


async def call(world, entry):
    await world.change_status.execute(1, world.user.id, entry.id, EntryStatus.CALLED)


async def test_leaving_while_waiting_is_a_cancellation(world):
    entry = (await world.join()).entry

    view = await world.leave_queue.execute(entry.public_token)

    assert view.entry.status is EntryStatus.CANCELLED
    event = world.events.items[-1]
    assert (event.event_type, event.from_status, event.actor) == (EventType.CANCELLED, EntryStatus.WAITING, Actor.DINER)
    assert world.publisher.kinds(host_topic(1))[-1] == "cancelled"


async def test_leaving_after_being_called_is_still_a_cancellation_not_a_no_show(world):
    entry = (await world.join()).entry
    await call(world, entry)

    view = await world.leave_queue.execute(entry.public_token)

    assert view.entry.status is EntryStatus.CANCELLED
    assert world.events.items[-1].from_status is EntryStatus.CALLED


async def test_repeating_leave_has_no_double_effect(world):
    entry = (await world.join()).entry
    await world.leave_queue.execute(entry.public_token)
    events_before = len(world.events.items)
    published_before = len(world.publisher.published)

    view = await world.leave_queue.execute(entry.public_token)

    assert view.entry.status is EntryStatus.CANCELLED
    assert len(world.events.items) == events_before
    assert len(world.publisher.published) == published_before


async def test_cannot_leave_after_being_seated(world):
    entry = (await world.join()).entry
    await call(world, entry)
    await world.change_status.execute(1, world.user.id, entry.id, EntryStatus.SEATED)

    with pytest.raises(InvalidTransition):
        await world.leave_queue.execute(entry.public_token)
    assert entry.status is EntryStatus.SEATED


async def test_on_the_way_is_an_alert_only(world):
    entry = (await world.join()).entry
    await call(world, entry)
    ends_at = (await world.get_entry_state.execute(entry.public_token)).hold_ends_at
    world.clock.advance(minutes=3)

    view = await world.notify_on_the_way.execute(entry.public_token)

    assert view.entry.status is EntryStatus.CALLED
    assert view.entry.on_the_way_at == world.clock.now()
    assert view.hold_ends_at == ends_at  # no extiende el plazo
    assert world.events.items[-1].event_type is EventType.ON_THE_WAY
    assert world.publisher.kinds(host_topic(1))[-1] == "on_the_way"


async def test_on_the_way_twice_has_no_double_effect(world):
    entry = (await world.join()).entry
    await call(world, entry)
    await world.notify_on_the_way.execute(entry.public_token)
    events_before = len(world.events.items)

    await world.notify_on_the_way.execute(entry.public_token)

    assert len(world.events.items) == events_before


async def test_on_the_way_before_being_called_is_invalid(world):
    entry = (await world.join()).entry
    with pytest.raises(InvalidTransition):
        await world.notify_on_the_way.execute(entry.public_token)


@pytest.mark.parametrize("action", ["leave_queue", "notify_on_the_way"])
async def test_unknown_token_is_not_found(world, action):
    with pytest.raises(NotFound):
        await getattr(world, action).execute("nope")


@pytest.mark.parametrize("action", ["leave_queue", "notify_on_the_way"])
async def test_a_token_from_another_venue_cannot_act_and_changes_nothing(world, action):
    entry = (await world.join()).entry
    await call(world, entry)
    events_before = len(world.events.items)

    with pytest.raises(NotFound):
        await getattr(world, action).execute(entry.public_token, "cuatro-vientos")

    assert entry.status is EntryStatus.CALLED and len(world.events.items) == events_before
