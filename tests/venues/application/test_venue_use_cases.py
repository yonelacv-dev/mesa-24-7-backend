from datetime import UTC, datetime, time

import pytest

from app.shared.application.errors import NotFound
from app.shared.domain.errors import ValidationFailed
from app.venues.application.realtime import host_topic, venue_topic
from app.venues.domain.enums import ListStatusKind
from app.venues.domain.schedule import DayWindow
from tests.support.world import SLUG

CLOSED_DAY = DayWindow(False, time(11, 0), time(23, 0))
EARLY = DayWindow(True, time(9, 0), time(15, 0))


async def test_status_of_an_open_venue(world):
    view = await world.venue_status.execute(SLUG)

    assert view.venue.name == "La Terraza Azul" and view.venue.phone_prefix == "+51"
    assert view.status.kind is ListStatusKind.OPEN and view.status.closes_at == time(1, 0)
    assert view.server_time == world.clock.now()


async def test_status_outside_hours_says_when_it_opens(world):
    world.clock.set(datetime(2026, 9, 18, 15, 0, tzinfo=UTC))  # viernes 10:00 Lima

    status = (await world.venue_status.execute(SLUG)).status

    assert status.kind is ListStatusKind.CLOSED
    assert (status.next_open.day_offset, status.next_open.time) == (0, time(11, 0))


async def test_status_unknown_venue_is_not_found(world):
    with pytest.raises(NotFound):
        await world.venue_status.execute("no-existe")


async def test_pause_and_resume_notify_diners_and_host(world):
    paused = await world.set_paused.execute(1, True)
    assert paused.status.kind is ListStatusKind.PAUSED and world.venue.paused

    resumed = await world.set_paused.execute(1, False)
    assert resumed.status.kind is ListStatusKind.OPEN and not world.venue.paused

    assert world.publisher.kinds(venue_topic(1)) == ["queue_changed", "queue_changed"]
    assert world.publisher.kinds(host_topic(1)) == ["paused", "resumed"]


async def test_pausing_twice_has_no_double_effect(world):
    await world.set_paused.execute(1, True)
    commits, published = world.uow.commits, len(world.publisher.published)

    await world.set_paused.execute(1, True)

    assert world.uow.commits == commits and len(world.publisher.published) == published


async def test_pause_only_affects_its_own_venue(world):
    await world.set_paused.execute(1, True)
    assert not world.other_venue.paused


async def test_pause_unknown_venue_is_not_found(world):
    with pytest.raises(NotFound):
        await world.set_paused.execute(999, True)


async def test_update_schedule_saves_and_notifies(world):
    week = (EARLY, *([CLOSED_DAY] * 6))  # solo lunes 09:00 a 15:00

    view = await world.update_schedule.execute(1, week)

    assert world.venue.schedule == week
    assert view.status.kind is ListStatusKind.CLOSED  # viernes 20:00 y solo abre lunes
    assert view.status.next_open.weekday == 0
    assert world.publisher.kinds(host_topic(1)) == ["schedule_updated"]
    assert world.publisher.kinds(venue_topic(1)) == ["queue_changed"]


async def test_update_schedule_rejects_equal_start_and_end_without_saving(world):
    original = world.venue.schedule
    bad = (DayWindow(True, time(11, 0), time(11, 0)), *original[1:])

    with pytest.raises(ValidationFailed) as error:
        await world.update_schedule.execute(1, bad)

    assert error.value.code == "schedule_start_equals_end"
    assert world.venue.schedule == original and world.uow.commits == 0


async def test_update_schedule_unknown_venue_is_not_found(world):
    with pytest.raises(NotFound):
        await world.update_schedule.execute(999, world.venue.schedule)


async def test_get_venue_by_id(world):
    from app.venues.application.use_cases.get_venue import GetVenueUseCase

    assert (await GetVenueUseCase(world.venues).execute(1)).slug == SLUG
    with pytest.raises(NotFound):
        await GetVenueUseCase(world.venues).execute(999)
