from abc import ABC, abstractmethod
from datetime import date

from app.waitlist.domain.entities import EntryEvent, QueueEntry
from app.waitlist.domain.enums import EntryStatus


class QueueEntryRepository(ABC):
    @abstractmethod
    async def add(self, entry: QueueEntry) -> QueueEntry:
        """Persiste la entrada nueva y le asigna su id. Lanza ActiveEntryAlreadyExists si el teléfono ya está activo."""

    @abstractmethod
    async def save(self, entry: QueueEntry) -> None: ...

    @abstractmethod
    async def get_by_token(self, token: str) -> QueueEntry | None: ...

    @abstractmethod
    async def get_by_token_for_update(self, token: str) -> QueueEntry | None:
        """Bloquea la fila hasta el commit, para que dos cambios simultáneos se serialicen."""

    @abstractmethod
    async def get_for_update(self, entry_id: int) -> QueueEntry | None: ...

    @abstractmethod
    async def get_active_by_phone(self, venue_id: int, phone_e164: str) -> QueueEntry | None: ...

    @abstractmethod
    async def list_active(self, venue_id: int) -> list[QueueEntry]:
        """Esperando y llamados de todas las jornadas del local, por orden de llegada."""

    @abstractmethod
    async def find_for_lookup(self, venue_id: int, ticket: int, phone_e164: str) -> QueueEntry | None:
        """La entrada más reciente con ese ticket y teléfono en el local."""

    @abstractmethod
    async def count_by_status(self, venue_id: int, service_date: date) -> dict[EntryStatus, int]: ...


class EntryEventRepository(ABC):
    @abstractmethod
    async def add(self, event: EntryEvent) -> EntryEvent: ...


class TicketCounter(ABC):
    @abstractmethod
    async def next_ticket(self, venue_id: int, service_date: date) -> int:
        """Siguiente correlativo de la jornada. Atómico: dos llamadas simultáneas nunca repiten número."""
