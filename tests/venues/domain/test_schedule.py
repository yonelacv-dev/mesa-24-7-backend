from datetime import UTC, date, datetime, time

import pytest

from app.shared.domain.errors import ValidationFailed
from app.venues.domain.entities import Venue
from app.venues.domain.enums import ListStatusKind
from app.venues.domain.schedule import DayWindow, evaluate_schedule, service_date_at, validate_schedule

CLOSED_DAY = DayWindow(False, time(11, 0), time(23, 0))
LATE_NIGHT = DayWindow(True, time(11, 0), time(1, 0))  # 11:00 a 01:00, cruza la medianoche
SAME_DAY = DayWindow(True, time(11, 0), time(23, 0))

# 2026-09-18 es viernes (weekday 4); 09-19 sábado; 09-21 lunes.
FRI_2000 = datetime(2026, 9, 18, 20, 0)
SAT_0030 = datetime(2026, 9, 19, 0, 30)


def week(default: DayWindow = LATE_NIGHT, **overrides: DayWindow) -> tuple[DayWindow, ...]:
    days = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
    return tuple(overrides.get(name, default) for name in days)


def test_open_inside_the_window():
    status = evaluate_schedule(week(), FRI_2000)
    assert status.is_open and status.closes_at == time(1, 0)


def test_window_crossing_midnight_is_still_open_after_00_00():
    status = evaluate_schedule(week(), SAT_0030)
    assert status.is_open and status.closes_at == time(1, 0)


def test_closing_time_is_exclusive_and_next_opening_is_today():
    status = evaluate_schedule(week(), datetime(2026, 9, 19, 1, 0))
    assert not status.is_open
    assert (status.next_open.day_offset, status.next_open.time) == (0, time(11, 0))


def test_start_time_is_inclusive():
    assert not evaluate_schedule(week(), datetime(2026, 9, 18, 10, 59)).is_open
    assert evaluate_schedule(week(), datetime(2026, 9, 18, 11, 0)).is_open


def test_crossing_window_of_a_closed_yesterday_does_not_apply():
    status = evaluate_schedule(week(fri=CLOSED_DAY), SAT_0030)
    assert not status.is_open
    assert status.next_open.day_offset == 0  # sábado 11:00


def test_same_day_window_closes_and_next_open_is_tomorrow():
    status = evaluate_schedule(week(SAME_DAY), datetime(2026, 9, 18, 23, 0))
    assert not status.is_open
    assert (status.next_open.day_offset, status.next_open.weekday, status.next_open.time) == (1, 5, time(11, 0))


def test_next_open_skips_closed_days():
    status = evaluate_schedule(week(CLOSED_DAY, mon=SAME_DAY), datetime(2026, 9, 19, 12, 0))  # sábado
    assert (status.next_open.day_offset, status.next_open.weekday) == (2, 0)


def test_next_open_can_be_same_weekday_next_week():
    status = evaluate_schedule(week(CLOSED_DAY, mon=SAME_DAY), datetime(2026, 9, 21, 23, 30))  # lunes tras cerrar
    assert (status.next_open.day_offset, status.next_open.weekday) == (7, 0)


def test_venue_without_any_open_day_has_no_next_open():
    status = evaluate_schedule(week(CLOSED_DAY), FRI_2000)
    assert not status.is_open and status.next_open is None


def test_service_date_of_a_window_that_crossed_midnight_is_the_day_it_started():
    assert service_date_at(week(), FRI_2000) == date(2026, 9, 18)
    assert service_date_at(week(), SAT_0030) == date(2026, 9, 18)
    assert service_date_at(week(), datetime(2026, 9, 19, 12, 0)) == date(2026, 9, 19)


def test_service_date_after_closing_is_the_last_started_window():
    assert service_date_at(week(), datetime(2026, 9, 19, 3, 0)) == date(2026, 9, 18)


def test_service_date_is_none_when_nothing_is_open():
    assert service_date_at(week(CLOSED_DAY), FRI_2000) is None


def test_validate_rejects_equal_start_and_end():
    with pytest.raises(ValidationFailed) as error:
        validate_schedule(week(fri=DayWindow(True, time(11, 0), time(11, 0))))
    assert error.value.code == "schedule_start_equals_end"


def test_validate_allows_equal_times_on_a_closed_day():
    validate_schedule(week(fri=DayWindow(False, time(11, 0), time(11, 0))))


def test_validate_requires_seven_days():
    with pytest.raises(ValidationFailed):
        validate_schedule(week()[:6])


def venue(timezone_name: str, paused: bool = False, country: str = "PE") -> Venue:
    return Venue(slug="v", name="V", country_code=country, timezone=timezone_name, paused=paused, schedule=week())


def test_paused_inside_hours_is_paused():
    status = venue("America/Lima", paused=True).status_at(datetime(2026, 9, 19, 1, 0, tzinfo=UTC))  # 20:00 Lima
    assert status.kind is ListStatusKind.PAUSED


def test_paused_outside_hours_shows_as_closed():
    status = venue("America/Lima", paused=True).status_at(datetime(2026, 9, 18, 15, 0, tzinfo=UTC))  # 10:00 Lima
    assert status.kind is ListStatusKind.CLOSED


def test_open_uses_the_venue_local_time_not_utc():
    v = venue("America/Lima")
    assert v.status_at(datetime(2026, 9, 19, 1, 0, tzinfo=UTC)).kind is ListStatusKind.OPEN  # 20:00 Lima
    assert v.status_at(datetime(2026, 9, 18, 15, 0, tzinfo=UTC)).kind is ListStatusKind.CLOSED  # 10:00 Lima


def test_santiago_summer_and_winter_offsets_are_respected():
    v = venue("America/Santiago", country="CL")
    # Mismo instante del día en UTC, distinto offset local (verano UTC-3, invierno UTC-4).
    summer = datetime(2026, 1, 10, 4, 30, tzinfo=UTC)  # 01:30 local, ya cerró
    winter = datetime(2026, 7, 11, 4, 30, tzinfo=UTC)  # 00:30 local, aún abierta
    assert v.status_at(summer).kind is ListStatusKind.CLOSED
    assert v.status_at(winter).kind is ListStatusKind.OPEN
