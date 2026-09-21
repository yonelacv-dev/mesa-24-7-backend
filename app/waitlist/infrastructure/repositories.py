from dataclasses import replace
from datetime import date

from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.waitlist.application.errors import ActiveEntryAlreadyExists
from app.waitlist.application.ports import EntryEventRepository, QueueEntryRepository, TicketCounter
from app.waitlist.domain.entities import EntryEvent, QueueEntry
from app.waitlist.domain.enums import ACTIVE_STATUSES, EntryStatus
from app.waitlist.infrastructure.models import EntryEventModel, QueueEntryModel

ACTIVE_PHONE_CONSTRAINT = "uq_queue_entry_venue_active_phone"


def _to_domain(model: QueueEntryModel) -> QueueEntry:
    return QueueEntry(
        id=model.id,
        venue_id=model.venue_id,
        public_token=model.public_token,
        service_date=model.service_date,
        ticket=model.ticket,
        name=model.name,
        phone_e164=model.phone_e164,
        party_size=model.party_size,
        status=model.status,
        joined_at=model.joined_at,
        consent_accepted_at=model.consent_accepted_at,
        consent_text_version=model.consent_text_version,
        called_at=model.called_at,
        on_the_way_at=model.on_the_way_at,
        ended_at=model.ended_at,
    )


class SQLAlchemyQueueEntryRepository(QueueEntryRepository):
    def __init__(self, session: AsyncSession):
        self._session = session

    async def add(self, entry: QueueEntry) -> QueueEntry:
        model = QueueEntryModel(
            venue_id=entry.venue_id,
            public_token=entry.public_token,
            service_date=entry.service_date,
            ticket=entry.ticket,
            name=entry.name,
            phone_e164=entry.phone_e164,
            party_size=entry.party_size,
            status=entry.status,
            consent_accepted_at=entry.consent_accepted_at,
            consent_text_version=entry.consent_text_version,
            joined_at=entry.joined_at,
        )
        self._session.add(model)
        try:
            await self._session.flush()
        except IntegrityError as error:
            if ACTIVE_PHONE_CONSTRAINT in str(error.orig):
                raise ActiveEntryAlreadyExists() from error
            raise
        entry.id = model.id
        return entry

    async def save(self, entry: QueueEntry) -> None:
        model = await self._session.get(QueueEntryModel, entry.id)
        model.status = entry.status
        model.called_at = entry.called_at
        model.on_the_way_at = entry.on_the_way_at
        model.ended_at = entry.ended_at
        await self._session.flush()

    async def get_by_token(self, token: str) -> QueueEntry | None:
        model = await self._session.scalar(select(QueueEntryModel).where(QueueEntryModel.public_token == token))
        return _to_domain(model) if model else None

    async def get_by_token_for_update(self, token: str) -> QueueEntry | None:
        query = select(QueueEntryModel).where(QueueEntryModel.public_token == token)
        return await self._locked(query)

    async def get_for_update(self, entry_id: int) -> QueueEntry | None:
        return await self._locked(select(QueueEntryModel).where(QueueEntryModel.id == entry_id))

    async def _locked(self, query) -> QueueEntry | None:
        # populate_existing: si la fila ya estaba en la sesión, se relee el estado real bajo el bloqueo.
        model = await self._session.scalar(query.with_for_update().execution_options(populate_existing=True))
        return _to_domain(model) if model else None

    async def get_active_by_phone(self, venue_id: int, phone_e164: str) -> QueueEntry | None:
        model = await self._session.scalar(
            select(QueueEntryModel).where(
                QueueEntryModel.venue_id == venue_id,
                QueueEntryModel.phone_e164 == phone_e164,
                QueueEntryModel.status.in_(ACTIVE_STATUSES),
            )
        )
        return _to_domain(model) if model else None

    async def list_active(self, venue_id: int) -> list[QueueEntry]:
        result = await self._session.scalars(
            select(QueueEntryModel)
            .where(QueueEntryModel.venue_id == venue_id, QueueEntryModel.status.in_(ACTIVE_STATUSES))
            .order_by(QueueEntryModel.joined_at, QueueEntryModel.id)
        )
        return [_to_domain(model) for model in result]

    async def find_for_lookup(self, venue_id: int, ticket: int, phone_e164: str) -> QueueEntry | None:
        model = await self._session.scalar(
            select(QueueEntryModel)
            .where(
                QueueEntryModel.venue_id == venue_id,
                QueueEntryModel.ticket == ticket,
                QueueEntryModel.phone_e164 == phone_e164,
            )
            .order_by(QueueEntryModel.service_date.desc(), QueueEntryModel.joined_at.desc())
            .limit(1)
        )
        return _to_domain(model) if model else None

    async def count_by_status(self, venue_id: int, service_date: date) -> dict[EntryStatus, int]:
        rows = await self._session.execute(
            select(QueueEntryModel.status, func.count())
            .where(QueueEntryModel.venue_id == venue_id, QueueEntryModel.service_date == service_date)
            .group_by(QueueEntryModel.status)
        )
        return {status: count for status, count in rows}


class SQLAlchemyEntryEventRepository(EntryEventRepository):
    def __init__(self, session: AsyncSession):
        self._session = session

    async def add(self, event: EntryEvent) -> EntryEvent:
        model = EntryEventModel(
            entry_id=event.entry_id,
            venue_id=event.venue_id,
            user_id=event.user_id,
            event_type=event.event_type,
            from_status=event.from_status,
            to_status=event.to_status,
            actor=event.actor,
            occurred_at=event.occurred_at,
        )
        self._session.add(model)
        await self._session.flush()
        return replace(event, id=model.id)


class SQLAlchemyTicketCounter(TicketCounter):
    """Correlativo por local y jornada, atómico en la base.

    `LAST_INSERT_ID(expr)` deja el valor en la conexión y el upsert toma un bloqueo sobre la fila del contador
    hasta el commit: dos "Unirme" simultáneos nunca reciben el mismo número, y si la transacción se deshace
    el número vuelve a estar disponible.
    """

    def __init__(self, session: AsyncSession):
        self._session = session

    async def next_ticket(self, venue_id: int, service_date: date) -> int:
        await self._session.execute(
            text(
                "INSERT INTO service_day_counter (venue_id, service_date, last_ticket) "
                "VALUES (:venue_id, :service_date, LAST_INSERT_ID(1)) "
                "ON DUPLICATE KEY UPDATE last_ticket = LAST_INSERT_ID(last_ticket + 1)"
            ),
            {"venue_id": venue_id, "service_date": service_date},
        )
        return int(await self._session.scalar(text("SELECT LAST_INSERT_ID()")))
