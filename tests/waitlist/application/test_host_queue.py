from datetime import UTC, datetime, timedelta

import pytest

from app.shared.application.errors import NotFound
from app.venues.domain.enums import ListStatusKind
from app.waitlist.domain.enums import EntryStatus

SAT_1200 = datetime(2026, 9, 19, 17, 0, tzinfo=UTC)  # sábado 12:00 Lima, jornada nueva


async def host_view(world):
    return await world.host_queue.execute(1)


async def test_empty_queue(world):
    view = await host_view(world)

    assert view.rows == [] and (view.waiting, view.called) == (0, 0)
    assert (view.finished.seated, view.finished.left, view.finished.no_show) == (0, 0, 0)
    assert view.status.kind is ListStatusKind.OPEN


async def test_rows_are_in_arrival_order_with_waiting_and_called_mixed(world):
    first, second, third = await world.join_many(3)
    await world.change_status.execute(1, world.user.id, second.entry.id, EntryStatus.CALLED)

    view = await host_view(world)

    assert [row.entry.ticket for row in view.rows] == [1, 2, 3]
    assert [row.entry.status for row in view.rows] == [EntryStatus.WAITING, EntryStatus.CALLED, EntryStatus.WAITING]
    assert (view.waiting, view.called) == (2, 1)


async def test_finished_summary_groups_cancelled_and_removed_as_left(world):
    a, b, c, d, e = await world.join_many(5)
    uid = world.user.id
    for entry in (a.entry, b.entry):
        await world.change_status.execute(1, uid, entry.id, EntryStatus.CALLED)
    await world.change_status.execute(1, uid, a.entry.id, EntryStatus.SEATED)
    await world.change_status.execute(1, uid, b.entry.id, EntryStatus.NO_SHOW)
    await world.leave_queue.execute(c.entry.public_token)
    await world.change_status.execute(1, uid, d.entry.id, EntryStatus.REMOVED)

    view = await host_view(world)

    assert (view.finished.seated, view.finished.left, view.finished.no_show) == (1, 2, 1)
    assert [row.entry.ticket for row in view.rows] == [5]  # solo queda quien sigue activo


async def test_hold_is_flagged_as_expired_only_after_the_configured_minutes(world):
    entry = (await world.join()).entry
    await world.change_status.execute(1, world.user.id, entry.id, EntryStatus.CALLED)

    world.clock.advance(minutes=10)
    assert (await host_view(world)).rows[0].hold_expired is False

    world.clock.advance(seconds=1)
    row = (await host_view(world)).rows[0]
    assert row.hold_expired is True
    assert row.hold_ends_at == entry.called_at + timedelta(minutes=10)


async def test_waiting_rows_have_no_hold(world):
    await world.join()
    row = (await host_view(world)).rows[0]
    assert row.hold_ends_at is None and row.hold_expired is False


async def test_finished_counts_only_the_current_service_day_but_active_rows_carry_over(world):
    old = (await world.join(phone="987654321")).entry
    await world.change_status.execute(1, world.user.id, old.id, EntryStatus.CALLED)
    await world.change_status.execute(1, world.user.id, old.id, EntryStatus.SEATED)
    pending = (await world.join(phone="987654322")).entry
    assert (await host_view(world)).finished.seated == 1

    world.clock.set(SAT_1200)
    view = await host_view(world)

    assert view.finished.seated == 0
    assert [row.entry.id for row in view.rows] == [pending.id]  # la gente de ayer se sigue atendiendo


async def test_view_reports_paused_and_closed_states(world):
    world.venue.paused = True
    assert (await host_view(world)).status.kind is ListStatusKind.PAUSED

    world.clock.set(datetime(2026, 9, 18, 15, 0, tzinfo=UTC))  # 10:00 Lima, fuera de horario
    view = await host_view(world)
    assert view.status.kind is ListStatusKind.CLOSED
    assert view.service_date is not None  # cerrada, pero se muestra el resumen de la última jornada


async def test_unknown_venue_is_not_found(world):
    with pytest.raises(NotFound):
        await world.host_queue.execute(999)
