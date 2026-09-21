from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Computed,
    Date,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.mysql import TINYINT
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.shared.infrastructure.types import UTC_NOW_SQL, UtcDateTime, utc_now
from app.waitlist.domain.enums import Actor, EntryStatus, EventType


def _enum(enum_class: type) -> Enum:
    # VARCHAR (no ENUM nativo de MySQL): agregar un estado no exige un ALTER de la columna.
    return Enum(
        enum_class,
        native_enum=False,
        length=16,
        validate_strings=True,
        create_constraint=False,
        values_callable=lambda cls: [member.value for member in cls],
    )


class QueueEntryModel(Base):
    __tablename__ = "queue_entry"
    __table_args__ = (
        UniqueConstraint("venue_id", "service_date", "ticket", name="uq_queue_entry_venue_service_ticket"),
        # Un teléfono, una entrada activa por local: la columna generada es NULL en estados finales
        # y MySQL no compara NULL en un índice único.
        UniqueConstraint("venue_id", "active_phone_key", name="uq_queue_entry_venue_active_phone"),
        CheckConstraint("party_size BETWEEN 1 AND 20", name="party_size_range"),
        Index("ix_queue_entry_venue_status_joined", "venue_id", "status", "joined_at"),
        Index("ix_queue_entry_venue_ticket", "venue_id", "ticket"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    venue_id: Mapped[int] = mapped_column(ForeignKey("venue.id"))
    public_token: Mapped[str] = mapped_column(String(64), unique=True)
    service_date: Mapped[date] = mapped_column(Date)
    ticket: Mapped[int] = mapped_column(Integer)
    name: Mapped[str] = mapped_column(String(60))
    phone_e164: Mapped[str] = mapped_column(String(16))
    party_size: Mapped[int] = mapped_column(TINYINT(unsigned=True))
    status: Mapped[EntryStatus] = mapped_column(_enum(EntryStatus))
    active_phone_key: Mapped[str | None] = mapped_column(
        String(16),
        Computed("IF(status IN ('waiting', 'called'), phone_e164, NULL)", persisted=True),
    )
    consent_accepted_at: Mapped[datetime] = mapped_column(UtcDateTime)
    consent_text_version: Mapped[str] = mapped_column(String(16))
    joined_at: Mapped[datetime] = mapped_column(UtcDateTime)
    called_at: Mapped[datetime | None] = mapped_column(UtcDateTime)
    on_the_way_at: Mapped[datetime | None] = mapped_column(UtcDateTime)
    ended_at: Mapped[datetime | None] = mapped_column(UtcDateTime)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, default=utc_now, server_default=UTC_NOW_SQL)
    updated_at: Mapped[datetime] = mapped_column(
        UtcDateTime, default=utc_now, onupdate=utc_now, server_default=UTC_NOW_SQL
    )


class EntryEventModel(Base):
    """Historial append-only: una fila por cada cambio de estado o aviso."""

    __tablename__ = "entry_event"
    __table_args__ = (
        Index("ix_entry_event_venue_occurred", "venue_id", "occurred_at"),
        Index("ix_entry_event_entry_occurred", "entry_id", "occurred_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    entry_id: Mapped[int] = mapped_column(ForeignKey("queue_entry.id"))
    venue_id: Mapped[int] = mapped_column(ForeignKey("venue.id"))
    user_id: Mapped[int | None] = mapped_column(ForeignKey("user.id"))
    event_type: Mapped[EventType] = mapped_column(_enum(EventType))
    from_status: Mapped[EntryStatus | None] = mapped_column(_enum(EntryStatus))
    to_status: Mapped[EntryStatus] = mapped_column(_enum(EntryStatus))
    actor: Mapped[Actor] = mapped_column(_enum(Actor))
    occurred_at: Mapped[datetime] = mapped_column(UtcDateTime)


class ServiceDayCounterModel(Base):
    __tablename__ = "service_day_counter"

    venue_id: Mapped[int] = mapped_column(ForeignKey("venue.id"), primary_key=True)
    service_date: Mapped[date] = mapped_column(Date, primary_key=True)
    last_ticket: Mapped[int] = mapped_column(Integer)
