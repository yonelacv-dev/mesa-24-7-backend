from datetime import time

from sqlalchemy import func, select

from app.seed import DEFAULT_WINDOW, DEMO_VENUES, seed
from app.venues.infrastructure.models import VenueModel, VenueScheduleModel
from app.waitlist.domain.enums import EntryStatus
from app.waitlist.infrastructure.models import QueueEntryModel

SLUG = "la-terraza-azul"


async def test_seed_creates_the_three_venues_with_a_default_schedule_and_a_user_each(db):
    credentials = await seed(db.factory, db.clock, password="demo-secreto")

    assert [c.username for c in credentials] == [v[4] for v in DEMO_VENUES]
    assert all(c.password == "demo-secreto" for c in credentials)
    async with db.factory() as session:
        assert await session.scalar(select(func.count()).select_from(VenueModel)) == 3
        assert await session.scalar(select(func.count()).select_from(VenueScheduleModel)) == 21
        tz = dict((await session.execute(select(VenueModel.slug, VenueModel.timezone))).all())
    assert tz["casa-mediterranea"] == "America/Santiago"


async def test_seed_is_idempotent_and_never_resets_existing_users(db):
    first = await seed(db.factory, db.clock)
    second = await seed(db.factory, db.clock)

    assert all(c.password for c in first) and all(c.password is None for c in second)
    async with db.factory() as session:
        assert await session.scalar(select(func.count()).select_from(VenueModel)) == 3


async def test_seed_generates_a_different_password_for_each_user(db):
    passwords = [c.password for c in await seed(db.factory, db.clock)]
    assert len(set(passwords)) == 3 and all(len(p) >= 12 for p in passwords)


async def test_by_default_the_schedule_is_the_real_business_window_not_24h(db):
    await seed(db.factory, db.clock)

    async with db.factory() as session:
        rows = (await session.scalars(select(VenueScheduleModel))).all()
    assert all((row.start_time, row.end_time) == DEFAULT_WINDOW for row in rows)


async def test_open_24h_opens_every_venue_and_is_idempotent(db):
    await seed(db.factory, db.clock, open_24h=True)
    await seed(db.factory, db.clock, open_24h=True)  # repetirlo no debe fallar ni cambiar el resultado

    async with db.factory() as session:
        rows = (await session.scalars(select(VenueScheduleModel))).all()
    assert len(rows) == 21  # 3 locales x 7 días
    assert all(row.is_open for row in rows)
    assert all((row.start_time, row.end_time) == (time(0, 0), time(23, 59)) for row in rows)


async def test_demo_queue_matches_the_brief(db):
    await seed(db.factory, db.clock, demo_queue=True)

    async with db.scope() as w:
        venue = await w.venues.get_by_slug(SLUG)
        view = await w.host_queue.execute(venue.id)
        state = await w.get_entry_state.execute(view.rows[2].entry.public_token)

    rows = view.rows
    assert [r.entry.ticket for r in rows] == [1, 2, 3, 4, 5]
    assert [r.entry.name for r in rows] == ["Familia Rojas", "Jorge P.", "Andrés V.", "Lucía y Ana", "Marco T."]
    assert [r.entry.party_size for r in rows] == [6, 2, 2, 2, 3]
    assert rows[0].entry.status is EntryStatus.CALLED and rows[0].hold_ends_at is not None
    assert (view.waiting, view.called) == (4, 1)
    assert state.position == 2  # los llamados no cuentan: Jorge es el 1, Andrés el 2


async def test_demo_queue_is_added_only_once(db):
    await seed(db.factory, db.clock, demo_queue=True)
    await seed(db.factory, db.clock, demo_queue=True)

    async with db.factory() as session:
        assert await session.scalar(select(func.count()).select_from(QueueEntryModel)) == 5
    async with db.scope() as w:  # el contador quedó en 5: el próximo que se una es el 6
        result = await w.join(SLUG, phone="987000111")
    assert result.entry.ticket == 6
