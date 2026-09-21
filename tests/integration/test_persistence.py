import asyncio
from datetime import UTC, date, datetime, time, timedelta, timezone

import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy.exc import DBAPIError, IntegrityError

import app.models_registry  # noqa: F401
from app.database import Base
from app.venues.domain.schedule import DayWindow
from app.waitlist.application.errors import ActiveEntryAlreadyExists
from app.waitlist.domain.entities import QueueEntry
from app.waitlist.domain.enums import Actor, EntryStatus, EventType

DAY = date(2026, 9, 18)
NOW = datetime(2026, 9, 19, 1, 0, tzinfo=UTC)


def make_entry(venue_id: int, phone: str = "+51987654321", ticket: int = 1, **kwargs) -> QueueEntry:
    return QueueEntry.join(
        venue_id=venue_id,
        public_token=kwargs.pop("token", f"tok-{venue_id}-{ticket}-{phone}"),
        service_date=kwargs.pop("service_date", DAY),
        ticket=ticket,
        name="Carla",
        phone_e164=phone,
        party_size=2,
        consent_accepted=True,
        consent_text_version="v1",
        now=kwargs.pop("now", NOW),
    )


async def test_models_and_migrations_are_in_sync(db):
    async with db.engine.connect() as conn:

        def diff(sync_conn):
            context = MigrationContext.configure(sync_conn, opts={"compare_type": True})
            return compare_metadata(context, Base.metadata)

        assert await conn.run_sync(diff) == []


async def test_datetimes_round_trip_as_utc_and_naive_ones_are_rejected(db):
    venue = await db.create_venue()
    lima = timezone(timedelta(hours=-5))
    async with db.scope() as w:
        await w.entries.add(make_entry(venue.id, now=datetime(2026, 9, 18, 20, 0, tzinfo=lima)))
        await w.uow.commit()
    async with db.scope() as w:
        (entry,) = await w.entries.list_active(venue.id)
    assert entry.joined_at == datetime(2026, 9, 19, 1, 0, tzinfo=UTC)
    assert entry.joined_at.tzinfo is UTC

    async with db.scope() as w:
        with pytest.raises(Exception, match="zona horaria"):
            await w.entries.add(make_entry(venue.id, phone="+51987654322", ticket=2, now=datetime(2026, 9, 19, 1, 0)))


async def test_a_phone_can_have_only_one_active_entry_per_venue(db):
    venue = await db.create_venue()
    other = await db.create_venue(slug="cuatro-vientos", name="Cuatro Vientos")

    async with db.scope() as w:
        first = await w.entries.add(make_entry(venue.id, ticket=1))
        await w.uow.commit()

    async with db.scope() as w:
        with pytest.raises(ActiveEntryAlreadyExists):
            await w.entries.add(make_entry(venue.id, ticket=2, token="second"))

    async with db.scope() as w:  # otro local: permitido
        await w.entries.add(make_entry(other.id, ticket=1, token="other-venue"))
        await w.uow.commit()

    async with db.scope() as w:  # terminada la anterior: permitido de nuevo
        entry = await w.entries.get_for_update(first.id)
        entry.transition(EntryStatus.CANCELLED, Actor.DINER, NOW)
        await w.entries.save(entry)
        await w.entries.add(make_entry(venue.id, ticket=3, token="third"))
        await w.uow.commit()


async def test_a_called_entry_still_blocks_the_phone(db):
    venue = await db.create_venue()
    async with db.scope() as w:
        entry = await w.entries.add(make_entry(venue.id))
        entry.transition(EntryStatus.CALLED, Actor.HOST, NOW)
        await w.entries.save(entry)
        await w.uow.commit()
    async with db.scope() as w:
        with pytest.raises(ActiveEntryAlreadyExists):
            await w.entries.add(make_entry(venue.id, ticket=2, token="second"))


async def test_other_integrity_errors_are_not_mistaken_for_a_duplicate_phone(db):
    venue = await db.create_venue()
    async with db.scope() as w:
        await w.entries.add(make_entry(venue.id, phone="+51987654321", ticket=1))
        await w.uow.commit()
    async with db.scope() as w:  # mismo local, jornada y ticket con otro teléfono
        with pytest.raises(IntegrityError):
            await w.entries.add(make_entry(venue.id, phone="+51987654322", ticket=1, token="dup-ticket"))


async def test_tickets_are_sequential_per_venue_and_service_day(db):
    a = await db.create_venue()
    b = await db.create_venue(slug="cuatro-vientos", name="Cuatro Vientos")
    async with db.scope() as w:
        got = [
            await w.tickets.next_ticket(a.id, DAY),
            await w.tickets.next_ticket(a.id, DAY),
            await w.tickets.next_ticket(b.id, DAY),
            await w.tickets.next_ticket(a.id, DAY + timedelta(days=1)),
            await w.tickets.next_ticket(a.id, DAY),
        ]
        await w.uow.commit()
    assert got == [1, 2, 1, 1, 3]


async def test_a_rolled_back_transaction_gives_the_ticket_back(db):
    venue = await db.create_venue()
    async with db.scope() as w:
        assert await w.tickets.next_ticket(venue.id, DAY) == 1
        await w.uow.rollback()
    async with db.scope() as w:
        assert await w.tickets.next_ticket(venue.id, DAY) == 1
        await w.uow.commit()


async def test_concurrent_requests_never_get_the_same_ticket(db):
    venue = await db.create_venue()

    async def take() -> int:
        async with db.scope() as w:
            ticket = await w.tickets.next_ticket(venue.id, DAY)
            await w.uow.commit()
            return ticket

    tickets = await asyncio.gather(*(take() for _ in range(25)))

    assert sorted(tickets) == list(range(1, 26))


async def test_schedule_and_pause_round_trip(db):
    venue = await db.create_venue()
    week = (DayWindow(True, time(19, 0), time(1, 30)), *([DayWindow(False, time(11, 0), time(23, 0))] * 6))
    async with db.scope() as w:
        venue.schedule, venue.paused, venue.hold_minutes = week, True, 7
        await w.venues.save(venue)
        await w.uow.commit()
    async with db.scope() as w:
        loaded = await w.venues.get_by_slug("la-terraza-azul")
    assert loaded.schedule == week and loaded.schedule[0].crosses_midnight
    assert loaded.paused and loaded.hold_minutes == 7


async def test_database_rejects_a_schedule_with_equal_start_and_end(db):
    venue = await db.create_venue()
    async with db.scope() as w:
        venue.schedule = (DayWindow(True, time(11, 0), time(11, 0)), *venue.schedule[1:])
        with pytest.raises(DBAPIError, match="start_differs_from_end_when_open"):  # MySQL lo reporta como 3819
            await w.venues.save(venue)


async def test_list_active_is_in_arrival_order_and_skips_finished_entries(db):
    venue = await db.create_venue()
    async with db.scope() as w:
        later = await w.entries.add(make_entry(venue.id, "+51987654322", 2, now=NOW + timedelta(minutes=5)))
        earlier = await w.entries.add(make_entry(venue.id, "+51987654321", 1, now=NOW))
        done = await w.entries.add(make_entry(venue.id, "+51987654323", 3, now=NOW + timedelta(minutes=9)))
        done.transition(EntryStatus.CANCELLED, Actor.DINER, NOW)
        await w.entries.save(done)
        await w.uow.commit()
    async with db.scope() as w:
        assert [e.id for e in await w.entries.list_active(venue.id)] == [earlier.id, later.id]


async def test_lookup_picks_the_most_recent_service_day_for_a_repeated_ticket_number(db):
    venue = await db.create_venue()
    async with db.scope() as w:
        await w.entries.add(make_entry(venue.id, ticket=1, service_date=DAY, token="old"))
        entry = await w.entries.get_by_token_for_update("old")
        entry.transition(EntryStatus.CANCELLED, Actor.DINER, NOW)
        await w.entries.save(entry)
        await w.entries.add(make_entry(venue.id, ticket=1, service_date=DAY + timedelta(days=1), token="new"))
        await w.uow.commit()
    async with db.scope() as w:
        found = await w.entries.find_for_lookup(venue.id, 1, "+51987654321")
    assert found.public_token == "new"


async def test_for_update_rereads_the_row_even_if_the_session_already_had_it(db):
    venue = await db.create_venue()
    async with db.scope() as w:
        entry = await w.entries.add(make_entry(venue.id, token="t"))
        await w.uow.commit()
    async with db.scope() as reader, db.scope() as writer:
        assert (await reader.entries.get_by_token("t")).status is EntryStatus.WAITING
        locked = await writer.entries.get_for_update(entry.id)
        locked.transition(EntryStatus.REMOVED, Actor.HOST, NOW)
        await writer.entries.save(locked)
        await writer.uow.commit()
        assert (await reader.entries.get_for_update(entry.id)).status is EntryStatus.REMOVED


async def test_events_are_stored_with_their_actor_and_user(db):
    venue = await db.create_venue()
    user = await db.create_user(venue.id)
    async with db.scope() as w:
        entry = await w.entries.add(make_entry(venue.id))
        joined = await w.events.add(entry.joined_event())
        called = entry.transition(EntryStatus.CALLED, Actor.HOST, NOW, user_id=user.id)
        stored = await w.events.add(called)
        await w.uow.commit()
    assert joined.id and stored.id > joined.id
    assert (stored.event_type, stored.actor, stored.user_id) == (EventType.CALLED, Actor.HOST, user.id)
