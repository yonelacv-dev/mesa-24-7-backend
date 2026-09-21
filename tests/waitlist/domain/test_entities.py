from datetime import UTC, date, datetime, timedelta

import pytest

from app.shared.domain.errors import ValidationFailed
from app.waitlist.domain.entities import QueueEntry
from app.waitlist.domain.enums import Actor, EntryStatus, EventType
from app.waitlist.domain.errors import ActorNotAllowed, InvalidTransition

NOW = datetime(2026, 9, 19, 1, 0, tzinfo=UTC)


def join(**overrides) -> QueueEntry:
    data = dict(
        venue_id=1,
        public_token="tok",
        service_date=date(2026, 9, 18),
        ticket=14,
        name="Carla",
        phone_e164="+51987654321",
        party_size=2,
        consent_accepted=True,
        consent_text_version="v1",
        now=NOW,
    )
    data.update(overrides)
    return QueueEntry.join(**data)


def called_entry() -> QueueEntry:
    entry = join()
    entry.id = 7
    entry.transition(EntryStatus.CALLED, Actor.HOST, NOW, user_id=3)
    return entry


def test_join_creates_a_waiting_entry_and_trims_the_name():
    entry = join(name="  Carla  ")
    assert entry.name == "Carla"
    assert entry.status is EntryStatus.WAITING
    assert entry.joined_at == NOW and entry.consent_accepted_at == NOW


@pytest.mark.parametrize(
    ("overrides", "code"),
    [
        ({"name": "   "}, "name_required"),
        ({"name": "x" * 61}, "name_too_long"),
        ({"party_size": 0}, "party_size_out_of_range"),
        ({"party_size": 21}, "party_size_out_of_range"),
        ({"consent_accepted": False}, "consent_required"),
    ],
)
def test_join_validations(overrides, code):
    with pytest.raises(ValidationFailed) as error:
        join(**overrides)
    assert error.value.code == code


@pytest.mark.parametrize("size", [1, 20])
def test_party_size_bounds_are_inclusive(size):
    assert join(party_size=size).party_size == size


def test_name_of_exactly_60_characters_is_accepted():
    assert len(join(name="x" * 60).name) == 60


def test_call_sets_called_at_and_records_who_did_it():
    entry = join()
    entry.id = 7
    event = entry.transition(EntryStatus.CALLED, Actor.HOST, NOW, user_id=3)
    assert entry.status is EntryStatus.CALLED and entry.called_at == NOW
    assert (event.event_type, event.from_status, event.to_status) == (
        EventType.CALLED,
        EntryStatus.WAITING,
        EntryStatus.CALLED,
    )
    assert event.actor is Actor.HOST and event.user_id == 3 and event.entry_id == 7


def test_repeated_call_does_not_duplicate_the_event_or_restart_the_hold():
    entry = called_entry()
    later = NOW + timedelta(minutes=3)
    assert entry.transition(EntryStatus.CALLED, Actor.HOST, later, user_id=4) is None
    assert entry.called_at == NOW


def test_diner_cancelling_after_being_called_is_cancelled_not_no_show():
    entry = called_entry()
    event = entry.transition(EntryStatus.CANCELLED, Actor.DINER, NOW + timedelta(minutes=2))
    assert entry.status is EntryStatus.CANCELLED and entry.ended_at is not None
    assert event.from_status is EntryStatus.CALLED and event.user_id is None


def test_a_final_state_cannot_be_left():
    entry = called_entry()
    entry.transition(EntryStatus.SEATED, Actor.HOST, NOW)
    with pytest.raises(InvalidTransition):
        entry.transition(EntryStatus.REMOVED, Actor.HOST, NOW)
    assert entry.status is EntryStatus.SEATED


def test_diner_cannot_call_or_seat():
    entry = join()
    with pytest.raises(ActorNotAllowed):
        entry.transition(EntryStatus.CALLED, Actor.DINER, NOW)


def test_on_the_way_is_only_an_alert_and_keeps_the_state_and_deadline():
    entry = called_entry()
    event = entry.mark_on_the_way(NOW + timedelta(minutes=5))
    assert entry.status is EntryStatus.CALLED
    assert entry.hold_ends_at(10) == NOW + timedelta(minutes=10)
    assert event.event_type is EventType.ON_THE_WAY and event.actor is Actor.DINER


def test_on_the_way_twice_is_a_noop():
    entry = called_entry()
    entry.mark_on_the_way(NOW)
    assert entry.mark_on_the_way(NOW + timedelta(minutes=1)) is None


def test_on_the_way_before_being_called_is_invalid():
    with pytest.raises(InvalidTransition):
        join().mark_on_the_way(NOW)


def test_hold_expires_after_the_configured_minutes():
    entry = called_entry()
    assert not entry.is_hold_expired(NOW + timedelta(minutes=10), 10)
    assert entry.is_hold_expired(NOW + timedelta(minutes=10, seconds=1), 10)
    assert entry.is_hold_expired(NOW + timedelta(minutes=5), 4)


def test_hold_only_applies_while_called():
    assert join().hold_ends_at(10) is None
