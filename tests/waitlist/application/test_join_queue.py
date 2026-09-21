from datetime import UTC, date, datetime

import pytest

from app.shared.application.errors import NotFound
from app.shared.domain.errors import ValidationFailed
from app.venues.application.realtime import host_topic, venue_topic
from app.venues.domain.errors import ListClosed, ListPaused
from app.waitlist.domain.entities import QueueEntry
from app.waitlist.domain.enums import Actor, EntryStatus, EventType
from tests.support.world import OTHER_SLUG

FRI_2000 = datetime(2026, 9, 19, 1, 0, tzinfo=UTC)  # viernes 20:00 Lima
FRI_1000 = datetime(2026, 9, 18, 15, 0, tzinfo=UTC)  # viernes 10:00 Lima, antes de abrir
SAT_0030 = datetime(2026, 9, 19, 5, 30, tzinfo=UTC)  # sábado 00:30 Lima, sigue la jornada del viernes
SAT_0200 = datetime(2026, 9, 19, 7, 0, tzinfo=UTC)  # sábado 02:00 Lima, ya cerró
SAT_1200 = datetime(2026, 9, 19, 17, 0, tzinfo=UTC)  # sábado 12:00 Lima, jornada nueva


async def test_join_creates_a_waiting_entry_with_the_first_ticket(world):
    result = await world.join(name="  Carla ", phone="987 654 321", party_size=3)

    entry = result.entry
    assert not result.already_in_queue
    assert (entry.ticket, entry.name, entry.party_size) == (1, "Carla", 3)
    assert entry.phone_e164 == "+51987654321"
    assert entry.status is EntryStatus.WAITING
    assert entry.service_date == date(2026, 9, 18)
    assert entry.public_token == "token-1"
    assert entry.consent_text_version == "v1"


async def test_join_records_the_joined_event_and_notifies_everyone(world):
    result = await world.join()

    (event,) = world.events.items
    assert (event.event_type, event.actor, event.entry_id) == (EventType.JOINED, Actor.DINER, result.entry.id)
    assert world.uow.commits == 1
    assert world.publisher.kinds(venue_topic(1)) == ["queue_changed"]
    assert world.publisher.kinds(host_topic(1)) == ["joined"]
    detail = world.publisher.published[-1][1].data
    assert (detail["ticket"], detail["name"], detail["party_size"]) == (1, "Carla", 2)


async def test_tickets_are_sequential_per_venue(world):
    first = await world.join_many(3)
    other = await world.join(slug=OTHER_SLUG)

    assert [r.entry.ticket for r in first] == [1, 2, 3]
    assert other.entry.ticket == 1


async def test_ticket_numbering_restarts_on_a_new_service_day_not_at_midnight(world):
    friday = await world.join(phone="987654321")
    world.clock.set(SAT_0030)
    after_midnight = await world.join(phone="987654322")
    world.clock.set(SAT_1200)
    saturday = await world.join(phone="987654323")

    assert (friday.entry.ticket, friday.entry.service_date) == (1, date(2026, 9, 18))
    assert (after_midnight.entry.ticket, after_midnight.entry.service_date) == (2, date(2026, 9, 18))
    assert (saturday.entry.ticket, saturday.entry.service_date) == (1, date(2026, 9, 19))


async def test_cannot_join_outside_the_schedule(world):
    world.clock.set(FRI_1000)
    with pytest.raises(ListClosed):
        await world.join()
    assert world.entries.items == [] and world.tickets.counters == {}


async def test_cannot_join_exactly_at_closing_time(world):
    world.clock.set(datetime(2026, 9, 19, 6, 0, tzinfo=UTC))  # sábado 01:00 Lima
    with pytest.raises(ListClosed):
        await world.join()


async def test_cannot_join_while_paused(world):
    world.venue.paused = True
    with pytest.raises(ListPaused):
        await world.join()
    assert world.entries.items == []


async def test_people_already_in_the_list_are_still_attended_after_closing(world):
    entry = (await world.join()).entry
    world.clock.set(SAT_0200)

    with pytest.raises(ListClosed):
        await world.join(phone="987654322")
    called = await world.change_status.execute(1, world.user.id, entry.id, EntryStatus.CALLED)
    seated = await world.change_status.execute(1, world.user.id, entry.id, EntryStatus.SEATED)

    assert called.called_at is not None and seated.status is EntryStatus.SEATED


async def test_same_phone_gets_its_existing_entry_instead_of_a_second_one(world):
    first = await world.join(phone="987654321")
    again = await world.join(name="Otra", phone="+51 987 654 321")

    assert again.already_in_queue
    assert again.entry is first.entry
    assert world.tickets.counters[(1, date(2026, 9, 18))] == 1
    assert len(world.events.items) == 1
    assert world.publisher.kinds(host_topic(1)) == ["joined"]


async def test_a_called_entry_still_blocks_a_second_one_with_the_same_phone(world):
    first = (await world.join()).entry
    await world.change_status.execute(1, world.user.id, first.id, EntryStatus.CALLED)

    again = await world.join()

    assert again.already_in_queue and again.entry is first


async def test_can_rejoin_with_a_new_ticket_after_the_previous_entry_ended(world):
    first = (await world.join()).entry
    await world.leave_queue.execute(first.public_token)

    second = await world.join()

    assert not second.already_in_queue
    assert second.entry is not first and second.entry.ticket == 2
    assert second.entry.status is EntryStatus.WAITING


async def test_the_same_phone_can_wait_in_two_different_venues(world):
    a = await world.join()
    b = await world.join(slug=OTHER_SLUG)

    assert not a.already_in_queue and not b.already_in_queue
    assert (a.entry.venue_id, b.entry.venue_id) == (1, 2)


async def test_invalid_phone_is_rejected_without_burning_a_ticket(world):
    with pytest.raises(ValidationFailed) as error:
        await world.join(phone="12345")
    assert error.value.code == "invalid_phone"
    assert world.tickets.counters == {} and world.entries.items == []


@pytest.mark.parametrize(
    ("overrides", "code"),
    [
        ({"name": "  "}, "name_required"),
        ({"name": "x" * 61}, "name_too_long"),
        ({"party_size": 21}, "party_size_out_of_range"),
        ({"consent": False}, "consent_required"),
    ],
)
async def test_invalid_data_is_rejected_without_burning_a_ticket(world, overrides, code):
    with pytest.raises(ValidationFailed) as error:
        await world.join(**overrides)
    assert error.value.code == code
    assert world.tickets.counters == {} and world.entries.items == []


async def test_losing_a_race_on_the_same_phone_returns_the_winner_and_rolls_back(world):
    now = world.clock.now()
    winner = QueueEntry.join(
        venue_id=1,
        public_token="winner",
        service_date=date(2026, 9, 18),
        ticket=1,
        name="Ganador",
        phone_e164="+51987654321",
        party_size=2,
        consent_accepted=True,
        consent_text_version="v1",
        now=now,
    )
    world.entries.race_winner = winner

    result = await world.join()

    assert result.already_in_queue and result.entry is winner
    assert world.uow.rollbacks == 1 and world.uow.commits == 0
    assert world.events.items == []


async def test_unknown_venue_is_not_found(world):
    with pytest.raises(NotFound):
        await world.join(slug="no-existe")
