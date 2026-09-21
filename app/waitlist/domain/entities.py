from dataclasses import dataclass
from datetime import date, datetime, timedelta

from app.shared.domain.errors import ValidationFailed
from app.waitlist.domain.enums import Actor, EntryStatus, EventType
from app.waitlist.domain.errors import InvalidTransition
from app.waitlist.domain.state_machine import Decision, decide

MAX_NAME_LENGTH = 60
MAX_PARTY_SIZE = 20


@dataclass(frozen=True)
class EntryEvent:
    entry_id: int | None
    venue_id: int
    event_type: EventType
    from_status: EntryStatus | None
    to_status: EntryStatus
    actor: Actor
    occurred_at: datetime
    user_id: int | None = None
    id: int | None = None


@dataclass
class QueueEntry:
    venue_id: int
    public_token: str
    service_date: date
    ticket: int
    name: str
    phone_e164: str
    party_size: int
    joined_at: datetime
    consent_accepted_at: datetime
    consent_text_version: str
    status: EntryStatus = EntryStatus.WAITING
    called_at: datetime | None = None
    on_the_way_at: datetime | None = None
    ended_at: datetime | None = None
    id: int | None = None

    @property
    def sort_key(self) -> tuple:
        return (self.joined_at, self.id or 0)

    @staticmethod
    def validate_join_data(name: str, party_size: int, consent_accepted: bool) -> str:
        """Valida lo que ingresa el comensal y devuelve el nombre limpio."""
        name = name.strip()
        if not name:
            raise ValidationFailed(
                "name_required", "Escribe tu nombre para que el anfitrión te encuentre.", field="name"
            )
        if len(name) > MAX_NAME_LENGTH:
            raise ValidationFailed(
                "name_too_long", f"El nombre admite hasta {MAX_NAME_LENGTH} caracteres.", field="name"
            )
        if not 1 <= party_size <= MAX_PARTY_SIZE:
            raise ValidationFailed(
                "party_size_out_of_range",
                f"Pueden ser de 1 a {MAX_PARTY_SIZE} personas. Si son más, habla con el anfitrión.",
                field="party_size",
            )
        if not consent_accepted:
            raise ValidationFailed("consent_required", "Debes aceptar que el anfitrión te llame.", field="consent")
        return name

    @classmethod
    def join(
        cls,
        *,
        venue_id: int,
        public_token: str,
        service_date: date,
        ticket: int,
        name: str,
        phone_e164: str,
        party_size: int,
        consent_accepted: bool,
        consent_text_version: str,
        now: datetime,
    ) -> "QueueEntry":
        name = cls.validate_join_data(name, party_size, consent_accepted)
        return cls(
            venue_id=venue_id,
            public_token=public_token,
            service_date=service_date,
            ticket=ticket,
            name=name,
            phone_e164=phone_e164,
            party_size=party_size,
            joined_at=now,
            consent_accepted_at=now,
            consent_text_version=consent_text_version,
        )

    def joined_event(self) -> EntryEvent:
        return EntryEvent(
            entry_id=self.id,
            venue_id=self.venue_id,
            event_type=EventType.JOINED,
            from_status=None,
            to_status=EntryStatus.WAITING,
            actor=Actor.DINER,
            occurred_at=self.joined_at,
        )

    def transition(
        self, target: EntryStatus, actor: Actor, now: datetime, user_id: int | None = None
    ) -> EntryEvent | None:
        """Aplica el cambio y devuelve su evento; None si ya estaba en ese estado (repetir no duplica)."""
        if decide(self.status, target, actor) is Decision.NOOP:
            return None
        previous = self.status
        self.status = target
        if target is EntryStatus.CALLED:
            self.called_at = now
        else:
            self.ended_at = now
        return EntryEvent(
            entry_id=self.id,
            venue_id=self.venue_id,
            event_type=EventType(target.value),
            from_status=previous,
            to_status=target,
            actor=actor,
            occurred_at=now,
            user_id=user_id if actor is Actor.HOST else None,
        )

    def mark_on_the_way(self, now: datetime) -> EntryEvent | None:
        """Aviso informativo: no cambia el estado ni extiende el plazo. Solo tiene sentido estando llamado."""
        if self.status is not EntryStatus.CALLED:
            raise InvalidTransition(
                "invalid_transition", "Solo puedes avisar que vas en camino después de ser llamado."
            )
        if self.on_the_way_at is not None:
            return None
        self.on_the_way_at = now
        return EntryEvent(
            entry_id=self.id,
            venue_id=self.venue_id,
            event_type=EventType.ON_THE_WAY,
            from_status=EntryStatus.CALLED,
            to_status=EntryStatus.CALLED,
            actor=Actor.DINER,
            occurred_at=now,
        )

    def hold_ends_at(self, hold_minutes: int) -> datetime | None:
        if self.status is not EntryStatus.CALLED or self.called_at is None:
            return None
        return self.called_at + timedelta(minutes=hold_minutes)

    def is_hold_expired(self, now: datetime, hold_minutes: int) -> bool:
        ends_at = self.hold_ends_at(hold_minutes)
        return ends_at is not None and now > ends_at
