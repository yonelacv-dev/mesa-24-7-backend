from datetime import UTC, date, datetime, timedelta

import pytest

from app.waitlist.domain.entities import QueueEntry
from app.waitlist.domain.enums import EntryStatus
from app.waitlist.domain.positioning import compute_positions, eta_range

MINUTES_PER_POSITION = 4
T0 = datetime(2026, 9, 18, 20, 0, tzinfo=UTC)


def entry(entry_id: int, minutes_after: int, status: EntryStatus = EntryStatus.WAITING) -> QueueEntry:
    joined = T0 + timedelta(minutes=minutes_after)
    return QueueEntry(
        id=entry_id,
        venue_id=1,
        public_token=f"tok{entry_id}",
        service_date=date(2026, 9, 18),
        ticket=entry_id,
        name=f"E{entry_id}",
        phone_e164=f"+5198765432{entry_id}",
        party_size=2,
        joined_at=joined,
        consent_accepted_at=joined,
        consent_text_version="v1",
        status=status,
    )


def test_position_is_one_plus_waiting_ahead():
    entries = [entry(1, 0), entry(2, 5), entry(3, 10)]
    assert compute_positions(entries) == {1: 1, 2: 2, 3: 3}


def test_called_entries_do_not_count_and_have_no_position():
    entries = [entry(1, 0, EntryStatus.CALLED), entry(2, 5), entry(3, 10)]
    assert compute_positions(entries) == {2: 1, 3: 2}


def test_calling_someone_in_the_middle_moves_up_only_those_behind():
    entries = [entry(1, 0), entry(2, 5), entry(3, 10), entry(4, 15)]
    entries[1].status = EntryStatus.CALLED
    assert compute_positions(entries) == {1: 1, 3: 2, 4: 3}


@pytest.mark.parametrize("gone", [EntryStatus.CANCELLED, EntryStatus.REMOVED, EntryStatus.SEATED, EntryStatus.NO_SHOW])
def test_entries_that_left_the_queue_free_their_spot(gone):
    entries = [entry(1, 0), entry(2, 5), entry(3, 10)]
    entries[0].status = gone
    assert compute_positions(entries) == {2: 1, 3: 2}


def test_order_is_by_arrival_not_by_input_order():
    entries = [entry(3, 10), entry(1, 0), entry(2, 5)]
    assert compute_positions(entries) == {1: 1, 2: 2, 3: 3}


def test_same_arrival_instant_breaks_ties_by_id():
    entries = [entry(2, 0), entry(1, 0)]
    assert compute_positions(entries) == {1: 1, 2: 2}


def test_empty_queue():
    assert compute_positions([]) == {}


@pytest.mark.parametrize(
    ("position", "expected"),
    [(1, (5, 10)), (2, (5, 10)), (3, (10, 15)), (7, (25, 35)), (10, (35, 50))],
)
def test_eta_range_examples(position, expected):
    assert eta_range(position, MINUTES_PER_POSITION) == expected


def test_eta_is_always_multiples_of_five_with_a_valid_range():
    for position in range(1, 41):
        low, high = eta_range(position, MINUTES_PER_POSITION)
        assert low % 5 == 0 and high % 5 == 0
        assert low >= 5
        assert high > low


def test_eta_respects_minutes_per_position_per_venue():
    assert eta_range(5, minutes_per_position=6) == (25, 40)


def test_eta_rounds_half_up_not_bankers():
    # 6 min/puesto, puesto 3 -> 18 min: el tope es 22.5, que debe subir a 25 (round() bancario daría 20)
    assert eta_range(3, minutes_per_position=6) == (15, 25)
