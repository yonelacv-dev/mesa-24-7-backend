"""Datos de demostración: 3 locales con su horario, un usuario por local y, opcionalmente, la cola de ejemplo.

    python -m app.seed                     # locales y usuarios
    python -m app.seed --demo-queue        # además, los comensales de ejemplo en La Terraza Azul
    python -m app.seed --open-24h          # además, los 3 locales abiertos 24h (solo para pruebas)

--open-24h también se puede pedir con la variable de entorno SEED_OPEN_24H=true (útil en Docker).
Es idempotente: lo que ya existe no se toca. Las contraseñas de los usuarios nuevos se generan al azar y se
muestran una sola vez (o se fija una con SEED_PASSWORD).
"""

import argparse
import asyncio
import os
import secrets
from dataclasses import dataclass
from datetime import time, timedelta

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.auth.domain.entities import User
from app.auth.infrastructure.argon2_hasher import Argon2PasswordHasher
from app.auth.infrastructure.repositories import SQLAlchemyUserRepository
from app.database import get_engine, get_session_factory
from app.shared.application.ports import Clock
from app.shared.infrastructure.clock import SystemClock
from app.shared.infrastructure.tokens import SecretsTokenGenerator
from app.venues.domain.entities import Venue
from app.venues.infrastructure.models import VenueModel, VenueScheduleModel
from app.venues.infrastructure.repository import SQLAlchemyVenueRepository
from app.waitlist.domain.entities import QueueEntry
from app.waitlist.domain.enums import Actor, EntryStatus
from app.waitlist.infrastructure.models import QueueEntryModel
from app.waitlist.infrastructure.repositories import (
    SQLAlchemyEntryEventRepository,
    SQLAlchemyQueueEntryRepository,
    SQLAlchemyTicketCounter,
)

# slug, nombre, país, zona horaria, usuario del local
DEMO_VENUES = [
    ("la-terraza-azul", "La Terraza Azul", "PE", "America/Lima", "terraza-azul"),
    ("cuatro-vientos", "Cuatro Vientos", "PE", "America/Lima", "cuatro-vientos"),
    ("casa-mediterranea", "Casa Mediterránea", "CL", "America/Santiago", "casa-mediterranea"),
]
DEFAULT_WINDOW = (time(11, 0), time(1, 0))  # 11:00 a 01:00 todos los días (supuesto del brief, editable)

# nombre, personas, teléfono, minutos desde que llegó, minutos desde que fue llamado (None = esperando)
DEMO_QUEUE = [
    ("Familia Rojas", 6, "+51944210333", 38, 4),
    ("Jorge P.", 2, "+51987118402", 31, None),
    ("Andrés V.", 2, "+51921774015", 22, None),
    ("Lucía y Ana", 2, "+51958302661", 15, None),
    ("Marco T.", 3, "+51966540178", 8, None),
]


@dataclass(frozen=True)
class Credential:
    venue: str
    username: str
    password: str | None  # None si el usuario ya existía


async def _ensure_venue(session: AsyncSession, slug: str, name: str, country: str, timezone: str) -> int:
    venue_id = await session.scalar(select(VenueModel.id).where(VenueModel.slug == slug))
    if venue_id is not None:
        return venue_id
    model = VenueModel(slug=slug, name=name, country_code=country, timezone=timezone)
    model.schedule = [
        VenueScheduleModel(weekday=day, is_open=True, start_time=DEFAULT_WINDOW[0], end_time=DEFAULT_WINDOW[1])
        for day in range(7)
    ]
    session.add(model)
    await session.flush()
    return model.id


async def _ensure_user(
    session: AsyncSession, hasher: Argon2PasswordHasher, venue_id: int, username: str, password: str | None
) -> tuple[User, str | None]:
    existing = await SQLAlchemyUserRepository(session).get_by_username(username)
    if existing is not None:
        return existing, None
    password = password or secrets.token_urlsafe(9)
    user = User(venue_id=venue_id, username=username, password_hash=await hasher.hash(password))
    await SQLAlchemyUserRepository(session).save(user)
    return user, password


async def _seed_demo_queue(session: AsyncSession, venue: Venue, host_user_id: int, clock: Clock) -> bool:
    """Los comensales de ejemplo del brief (tickets 1 al 5). Solo si el local no tiene entradas todavía."""
    if await session.scalar(
        select(func.count()).select_from(QueueEntryModel).where(QueueEntryModel.venue_id == venue.id)
    ):
        return False
    now = clock.now()
    service_date = venue.service_date_at(now) or venue.local_now(now).date()
    entries = SQLAlchemyQueueEntryRepository(session)
    events = SQLAlchemyEntryEventRepository(session)
    tickets = SQLAlchemyTicketCounter(session)
    tokens = SecretsTokenGenerator()

    for name, party_size, phone, minutes_ago, called_minutes_ago in DEMO_QUEUE:
        entry = QueueEntry.join(
            venue_id=venue.id,
            public_token=tokens.new_token(),
            service_date=service_date,
            ticket=await tickets.next_ticket(venue.id, service_date),
            name=name,
            phone_e164=phone,
            party_size=party_size,
            consent_accepted=True,
            consent_text_version="v1",
            now=now - timedelta(minutes=minutes_ago),
        )
        await entries.add(entry)
        await events.add(entry.joined_event())
        if called_minutes_ago is not None:
            called = entry.transition(
                EntryStatus.CALLED, Actor.HOST, now - timedelta(minutes=called_minutes_ago), user_id=host_user_id
            )
            await entries.save(entry)
            await events.add(called)
    return True


async def _open_all_schedules(session: AsyncSession) -> None:
    """Deja todos los locales abiertos las 24 horas. Solo para un servidor de pruebas: no es horario real."""
    await session.execute(
        update(VenueScheduleModel).values(is_open=True, start_time=time(0, 0), end_time=time(23, 59))
    )


async def seed(
    session_factory: async_sessionmaker[AsyncSession],
    clock: Clock,
    *,
    demo_queue: bool = False,
    password: str | None = None,
    open_24h: bool = False,
) -> list[Credential]:
    hasher = Argon2PasswordHasher()
    credentials: list[Credential] = []
    async with session_factory() as session:
        for slug, name, country, timezone, username in DEMO_VENUES:
            venue_id = await _ensure_venue(session, slug, name, country, timezone)
            user, generated = await _ensure_user(session, hasher, venue_id, username, password)
            credentials.append(Credential(name, username, generated))
            if demo_queue and slug == "la-terraza-azul":
                await session.commit()  # el local y su horario tienen que estar guardados para releerlos
                async with session_factory() as fresh:
                    venue = await SQLAlchemyVenueRepository(fresh).get_by_id(venue_id)
                    if await _seed_demo_queue(fresh, venue, user.id, clock):
                        await fresh.commit()
        if open_24h:
            await _open_all_schedules(session)
        await session.commit()
    return credentials


async def _main(demo_queue: bool, open_24h: bool) -> None:
    credentials = await seed(
        get_session_factory(),
        SystemClock(),
        demo_queue=demo_queue,
        password=os.environ.get("SEED_PASSWORD"),
        open_24h=open_24h,
    )
    print(f"{'Local':<22}{'Usuario':<22}Contraseña")
    for c in credentials:
        print(f"{c.venue:<22}{c.username:<22}{c.password or '(ya existía, sin cambios)'}")
    if any(c.password for c in credentials):
        print("\nGuarda estas contraseñas: no se vuelven a mostrar.")
    if open_24h:
        print("Los 3 locales quedaron abiertos las 24 horas (solo para pruebas).")
    await get_engine().dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--demo-queue", action="store_true", help="agrega los comensales de ejemplo del brief")
    parser.add_argument(
        "--open-24h", action="store_true", help="deja los 3 locales abiertos 24h (no es horario real; solo pruebas)"
    )
    args = parser.parse_args()
    env_open_24h = os.environ.get("SEED_OPEN_24H", "").strip().lower() == "true"
    asyncio.run(_main(args.demo_queue, args.open_24h or env_open_24h))
