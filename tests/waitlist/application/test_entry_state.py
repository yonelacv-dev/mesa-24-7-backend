from datetime import timedelta

import pytest

from app.shared.application.errors import NotFound
from app.waitlist.domain.enums import EntryStatus


async def state(world, result):
    return await world.get_entry_state.execute(result.entry.public_token)


async def test_waiting_entry_has_position_and_eta(world):
    first, _, third = await world.join_many(3)

    view1, view3 = await state(world, first), await state(world, third)

    assert (view1.position, view1.eta) == (1, (5, 10))
    assert (view3.position, view3.eta) == (3, (10, 15))
    assert view3.server_time == world.clock.now()


async def test_calling_someone_ahead_moves_up_the_ones_behind(world):
    first, second, third = await world.join_many(3)

    await world.change_status.execute(1, world.user.id, first.entry.id, EntryStatus.CALLED)

    assert (await state(world, second)).position == 1
    assert (await state(world, third)).position == 2


async def test_host_can_call_someone_who_is_not_first(world):
    first, second, third = await world.join_many(3)

    await world.change_status.execute(1, world.user.id, second.entry.id, EntryStatus.CALLED)

    assert (await state(world, first)).position == 1
    assert (await state(world, third)).position == 2  # los de atrás suben; el primero se queda


async def test_position_goes_down_when_someone_ahead_cancels_or_is_removed(world):
    first, second, third = await world.join_many(3)

    await world.leave_queue.execute(first.entry.public_token)
    await world.change_status.execute(1, world.user.id, second.entry.id, EntryStatus.REMOVED)

    assert (await state(world, third)).position == 1


async def test_called_entry_has_no_position_and_a_countdown(world):
    entry = (await world.join()).entry
    world.clock.advance(minutes=1)
    await world.change_status.execute(1, world.user.id, entry.id, EntryStatus.CALLED)
    called_at = world.clock.now()

    view = await world.get_entry_state.execute(entry.public_token)

    assert view.position is None and view.eta is None
    assert view.hold_ends_at == called_at + timedelta(minutes=10)


async def test_hold_time_is_configurable_per_venue(world):
    world.venue.hold_minutes = 5
    entry = (await world.join()).entry
    await world.change_status.execute(1, world.user.id, entry.id, EntryStatus.CALLED)

    view = await world.get_entry_state.execute(entry.public_token)

    assert view.hold_ends_at == world.clock.now() + timedelta(minutes=5)


async def test_eta_uses_the_venue_minutes_per_position(world):
    world.venue.minutes_per_position = 6
    results = await world.join_many(3)

    assert (await state(world, results[2])).eta == (15, 25)


async def test_unknown_token_is_not_found(world):
    with pytest.raises(NotFound):
        await world.get_entry_state.execute("nope")


async def test_a_token_only_works_in_the_venue_it_belongs_to(world):
    entry = (await world.join()).entry
    with pytest.raises(NotFound):
        await world.get_entry_state.execute(entry.public_token, "cuatro-vientos")
    assert (await world.get_entry_state.execute(entry.public_token, "la-terraza-azul")).entry is entry
