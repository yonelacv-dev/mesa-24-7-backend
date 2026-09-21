import asyncio

import pytest
from sqlalchemy import func, select, text

from app.auth.application.errors import InvalidCredentials, InvalidToken
from app.auth.domain.tokens import hash_token
from app.auth.infrastructure.models import AuthModel
from app.shared.application.errors import NotFound
from app.venues.application.realtime import host_topic, venue_topic
from app.waitlist.domain.enums import EntryStatus, EventType
from app.waitlist.domain.errors import InvalidTransition
from app.waitlist.infrastructure.models import EntryEventModel, QueueEntryModel

SLUG = "la-terraza-azul"


async def event_types(db, entry_id: int) -> list[EventType]:
    async with db.factory() as session:
        rows = await session.scalars(
            select(EntryEventModel.event_type).where(EntryEventModel.entry_id == entry_id).order_by(EntryEventModel.id)
        )
        return list(rows)


async def test_full_flow_join_call_seat_with_real_database(db):
    venue = await db.create_venue()
    user = await db.create_user(venue.id)

    async with db.scope() as w:
        joined = (await w.join(SLUG)).entry
    assert joined.ticket == 1 and joined.status is EntryStatus.WAITING

    async with db.scope() as w:
        state = await w.get_entry_state.execute(joined.public_token)
        assert (state.position, state.eta) == (1, (5, 10))
        await w.change_status.execute(venue.id, user.id, joined.id, EntryStatus.CALLED)
    async with db.scope() as w:
        await w.notify_on_the_way.execute(joined.public_token)
        await w.change_status.execute(venue.id, user.id, joined.id, EntryStatus.SEATED)
        view = await w.host_queue.execute(venue.id)
    assert view.rows == [] and view.finished.seated == 1

    assert await event_types(db, joined.id) == [
        EventType.JOINED,
        EventType.CALLED,
        EventType.ON_THE_WAY,
        EventType.SEATED,
    ]


async def test_same_phone_returns_the_existing_entry_and_can_rejoin_after_leaving(db):
    await db.create_venue()
    async with db.scope() as w:
        first = await w.join(SLUG, phone="987 654 321")
    async with db.scope() as w:
        again = await w.join(SLUG, phone="+51987654321")
    assert again.already_in_queue and again.entry.id == first.entry.id

    async with db.scope() as w:
        await w.leave_queue.execute(first.entry.public_token)
    async with db.scope() as w:
        rejoined = await w.join(SLUG)
    assert not rejoined.already_in_queue and rejoined.entry.ticket == 2


async def test_ticket_lookup_needs_the_right_phone(db):
    await db.create_venue()
    async with db.scope() as w:
        entry = (await w.join(SLUG, phone="987654321")).entry
    async with db.scope() as w:
        assert (await w.lookup(SLUG, 1, "987 654 321")).entry.id == entry.id
        for ticket, phone in ((1, "987654322"), (2, "987654321"), (1, "123")):
            with pytest.raises(NotFound):
                await w.lookup(SLUG, ticket, phone)


async def test_simultaneous_joins_with_the_same_phone_create_a_single_entry(db):
    await db.create_venue()

    async def join():
        async with db.scope() as w:
            return await w.join(SLUG, phone="987654321")

    results = await asyncio.gather(*(join() for _ in range(6)))

    assert len({r.entry.id for r in results}) == 1
    assert sum(1 for r in results if not r.already_in_queue) == 1
    async with db.factory() as session:
        assert await session.scalar(select(func.count()).select_from(QueueEntryModel)) == 1
        assert await session.scalar(select(func.count()).select_from(EntryEventModel)) == 1
    async with db.scope() as w:  # los tickets perdidos en la carrera se devolvieron: el siguiente es el 2
        assert (await w.join(SLUG, phone="987654322")).entry.ticket == 2


async def test_simultaneous_joins_with_different_phones_get_distinct_consecutive_tickets(db):
    await db.create_venue()

    async def join(i: int):
        async with db.scope() as w:
            return await w.join(SLUG, phone=f"9876543{i:02d}", name=f"Comensal {i}")

    results = await asyncio.gather(*(join(i) for i in range(20)))

    assert sorted(r.entry.ticket for r in results) == list(range(1, 21))


async def test_two_hosts_calling_the_same_row_at_once_apply_it_once(db):
    venue = await db.create_venue()
    user = await db.create_user(venue.id)
    async with db.scope() as w:
        entry = (await w.join(SLUG)).entry

    async def call():
        async with db.scope() as w:
            return await w.change_status.execute(venue.id, user.id, entry.id, EntryStatus.CALLED)

    results = await asyncio.gather(call(), call(), call())

    assert all(r.status is EntryStatus.CALLED for r in results)
    assert len({r.called_at for r in results}) == 1  # el plazo se fijó una sola vez
    assert await event_types(db, entry.id) == [EventType.JOINED, EventType.CALLED]


async def test_host_action_on_an_entry_the_other_host_already_closed_is_rejected_with_no_double_effect(db):
    venue = await db.create_venue()
    user = await db.create_user(venue.id)
    async with db.scope() as w:
        entry = (await w.join(SLUG)).entry

    async def remove():
        async with db.scope() as w:
            return await w.change_status.execute(venue.id, user.id, entry.id, EntryStatus.REMOVED)

    async def call():
        async with db.scope() as w:
            return await w.change_status.execute(venue.id, user.id, entry.id, EntryStatus.CALLED)

    outcomes = await asyncio.gather(remove(), call(), return_exceptions=True)

    async with db.scope() as w:
        final = (await w.get_entry_state.execute(entry.public_token)).entry
    types = await event_types(db, entry.id)
    assert final.status in (EntryStatus.REMOVED,)  # quitar gana siempre: si llamar iba primero, quitar aplica después
    assert types.count(EventType.REMOVED) == 1
    # Si 'llamar' llegó después de 'quitar' debe haber fallado limpiamente, sin dejar un evento de más.
    if types == [EventType.JOINED, EventType.REMOVED]:
        assert any(isinstance(o, InvalidTransition) for o in outcomes)


async def test_diner_cancelling_and_host_seating_at_once_never_leave_contradictory_history(db):
    venue = await db.create_venue()
    user = await db.create_user(venue.id)
    async with db.scope() as w:
        entry = (await w.join(SLUG)).entry
        await w.change_status.execute(venue.id, user.id, entry.id, EntryStatus.CALLED)

    async def seat():
        async with db.scope() as w:
            return await w.change_status.execute(venue.id, user.id, entry.id, EntryStatus.SEATED)

    async def leave():
        async with db.scope() as w:
            return await w.leave_queue.execute(entry.public_token)

    await asyncio.gather(seat(), leave(), return_exceptions=True)

    types = await event_types(db, entry.id)
    finals = [t for t in types if t in (EventType.SEATED, EventType.CANCELLED)]
    assert len(finals) == 1  # exactamente un desenlace: o se sentó o canceló, nunca ambos


async def test_events_are_published_only_after_the_commit(db):
    venue = await db.create_venue()
    async with db.broker.subscribe(venue_topic(venue.id)) as diners, db.broker.subscribe(host_topic(venue.id)) as host:
        async with db.scope() as w:
            await w.join(SLUG)
        assert (await asyncio.wait_for(diners.get(), 1)).kind == "queue_changed"
        assert (await asyncio.wait_for(host.get(), 1)).kind == "joined"


async def test_login_stores_only_the_token_hash_and_supports_two_tablets(db):
    venue = await db.create_venue()
    await db.create_user(venue.id, "terraza", "secreto")

    async with db.scope() as w:
        first = await w.login.execute("terraza", "secreto", "Tablet 1")
    async with db.scope() as w:
        second = await w.login.execute("terraza", "secreto", "Tablet 2")
        assert (await w.authenticate.execute(first.token)).venue_id == venue.id
        assert (await w.authenticate.execute(second.token)).venue_id == venue.id

    async with db.factory() as session:
        hashes = set(await session.scalars(select(AuthModel.token_hash)))
    assert hashes == {hash_token(first.token), hash_token(second.token)}
    assert first.token not in hashes

    async with db.scope() as w:
        await w.logout.execute(first.token)
    async with db.scope() as w:
        with pytest.raises(InvalidToken):
            await w.authenticate.execute(first.token)
        assert (await w.authenticate.execute(second.token)).username == "terraza"


async def test_login_rejects_wrong_password_and_unknown_user_identically(db):
    venue = await db.create_venue()
    await db.create_user(venue.id, "terraza", "secreto")
    async with db.scope() as w:
        with pytest.raises(InvalidCredentials) as wrong:
            await w.login.execute("terraza", "mala")
        with pytest.raises(InvalidCredentials) as unknown:
            await w.login.execute("nadie", "secreto")
    assert wrong.value.message == unknown.value.message


async def test_password_is_stored_hashed_with_argon2(db):
    venue = await db.create_venue()
    await db.create_user(venue.id, "terraza", "secreto")
    async with db.factory() as session:
        stored = await session.scalar(text("SELECT password_hash FROM `user` WHERE username = 'terraza'"))
    assert stored.startswith("$argon2") and "secreto" not in stored
