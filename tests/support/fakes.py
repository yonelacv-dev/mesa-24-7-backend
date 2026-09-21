"""Adaptadores en memoria de los puertos, solo para pruebas de la capa application."""

from dataclasses import replace
from datetime import date, datetime, timedelta

from app.auth.application.ports import AuthSessionRepository, PasswordHasher, UserRepository
from app.auth.domain.entities import AuthSession, User
from app.shared.application.ports import Clock, RealtimeEvent, RealtimePublisher, TokenGenerator, UnitOfWork
from app.venues.application.ports import VenueRepository
from app.venues.domain.entities import Venue
from app.waitlist.application.errors import ActiveEntryAlreadyExists
from app.waitlist.application.ports import EntryEventRepository, QueueEntryRepository, TicketCounter
from app.waitlist.domain.entities import EntryEvent, QueueEntry
from app.waitlist.domain.enums import ACTIVE_STATUSES, EntryStatus


class FakeClock(Clock):
    def __init__(self, now: datetime):
        self._now = now

    def now(self) -> datetime:
        return self._now

    def advance(self, **kwargs) -> None:
        self._now += timedelta(**kwargs)

    def set(self, now: datetime) -> None:
        self._now = now


class SequentialTokens(TokenGenerator):
    def __init__(self) -> None:
        self._n = 0

    def new_token(self) -> str:
        self._n += 1
        return f"token-{self._n}"


class FakeUnitOfWork(UnitOfWork):
    def __init__(self) -> None:
        self.commits = 0
        self.rollbacks = 0

    async def commit(self) -> None:
        self.commits += 1

    async def rollback(self) -> None:
        self.rollbacks += 1


class RecordingPublisher(RealtimePublisher):
    def __init__(self) -> None:
        self.published: list[tuple[str, RealtimeEvent]] = []

    async def publish(self, topic: str, event: RealtimeEvent) -> None:
        self.published.append((topic, event))

    def kinds(self, topic: str) -> list[str]:
        return [event.kind for t, event in self.published if t == topic]


class InMemoryVenues(VenueRepository):
    def __init__(self) -> None:
        self.items: dict[int, Venue] = {}

    def add(self, venue: Venue) -> Venue:
        self.items[venue.id] = venue
        return venue

    async def get_by_id(self, venue_id: int) -> Venue | None:
        return self.items.get(venue_id)

    async def get_by_slug(self, slug: str) -> Venue | None:
        return next((v for v in self.items.values() if v.slug == slug), None)

    async def save(self, venue: Venue) -> None:
        self.items[venue.id] = venue


class InMemoryEntries(QueueEntryRepository):
    def __init__(self) -> None:
        self.items: list[QueueEntry] = []
        self._next_id = 1
        # Simula que otro "Unirme" del mismo teléfono gana la carrera justo antes del INSERT.
        self.race_winner: QueueEntry | None = None

    def _has_active_phone(self, venue_id: int, phone: str) -> bool:
        return any(e.venue_id == venue_id and e.phone_e164 == phone and e.status in ACTIVE_STATUSES for e in self.items)

    async def add(self, entry: QueueEntry) -> QueueEntry:
        if self.race_winner is not None:
            winner, self.race_winner = self.race_winner, None
            winner.id = self._next_id
            self._next_id += 1
            self.items.append(winner)
            raise ActiveEntryAlreadyExists()
        if self._has_active_phone(entry.venue_id, entry.phone_e164):
            raise ActiveEntryAlreadyExists()
        entry.id = self._next_id
        self._next_id += 1
        self.items.append(entry)
        return entry

    async def save(self, entry: QueueEntry) -> None:
        pass  # los objetos se comparten por referencia

    async def get_by_token(self, token: str) -> QueueEntry | None:
        return next((e for e in self.items if e.public_token == token), None)

    async def get_by_token_for_update(self, token: str) -> QueueEntry | None:
        return await self.get_by_token(token)

    async def get_for_update(self, entry_id: int) -> QueueEntry | None:
        return next((e for e in self.items if e.id == entry_id), None)

    async def get_active_by_phone(self, venue_id: int, phone_e164: str) -> QueueEntry | None:
        return next(
            (
                e
                for e in self.items
                if e.venue_id == venue_id and e.phone_e164 == phone_e164 and e.status in ACTIVE_STATUSES
            ),
            None,
        )

    async def list_active(self, venue_id: int) -> list[QueueEntry]:
        active = [e for e in self.items if e.venue_id == venue_id and e.status in ACTIVE_STATUSES]
        return sorted(active, key=lambda e: e.sort_key)

    async def find_for_lookup(self, venue_id: int, ticket: int, phone_e164: str) -> QueueEntry | None:
        matches = [
            e for e in self.items if e.venue_id == venue_id and e.ticket == ticket and e.phone_e164 == phone_e164
        ]
        return max(matches, key=lambda e: (e.service_date, e.joined_at), default=None)

    async def count_by_status(self, venue_id: int, service_date: date) -> dict[EntryStatus, int]:
        counts: dict[EntryStatus, int] = {}
        for e in self.items:
            if e.venue_id == venue_id and e.service_date == service_date:
                counts[e.status] = counts.get(e.status, 0) + 1
        return counts


class InMemoryEvents(EntryEventRepository):
    def __init__(self) -> None:
        self.items: list[EntryEvent] = []

    async def add(self, event: EntryEvent) -> EntryEvent:
        stored = replace(event, id=len(self.items) + 1)
        self.items.append(stored)
        return stored


class InMemoryTickets(TicketCounter):
    def __init__(self) -> None:
        self.counters: dict[tuple[int, date], int] = {}

    async def next_ticket(self, venue_id: int, service_date: date) -> int:
        key = (venue_id, service_date)
        self.counters[key] = self.counters.get(key, 0) + 1
        return self.counters[key]


class InMemoryUsers(UserRepository):
    def __init__(self) -> None:
        self.items: dict[int, User] = {}

    def add(self, user: User) -> User:
        self.items[user.id] = user
        return user

    async def get_by_id(self, user_id: int) -> User | None:
        return self.items.get(user_id)

    async def get_by_username(self, username: str) -> User | None:
        return next((u for u in self.items.values() if u.username == username), None)

    async def save(self, user: User) -> None:
        self.items[user.id] = user


class InMemorySessions(AuthSessionRepository):
    def __init__(self) -> None:
        self.items: list[AuthSession] = []

    async def add(self, session: AuthSession) -> AuthSession:
        session.id = len(self.items) + 1
        self.items.append(session)
        return session

    async def get_by_token_hash(self, token_hash: str) -> AuthSession | None:
        return next((s for s in self.items if s.token_hash == token_hash), None)

    async def save(self, session: AuthSession) -> None:
        pass


class FakeHasher(PasswordHasher):
    def __init__(self) -> None:
        self.burns = 0

    async def hash(self, password: str) -> str:
        return f"hashed:{password}"

    async def verify(self, password_hash: str, password: str) -> bool:
        return password_hash == f"hashed:{password}"

    async def burn(self, password: str) -> None:
        self.burns += 1
