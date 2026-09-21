from app.shared.application.errors import NotFound
from app.shared.application.ports import Clock, RealtimePublisher, UnitOfWork
from app.waitlist.application.ports import EntryEventRepository, QueueEntryRepository
from app.waitlist.application.realtime import announce_entry_event
from app.waitlist.domain.entities import QueueEntry
from app.waitlist.domain.enums import Actor, EntryStatus


class ChangeEntryStatusUseCase:
    """Acciones del anfitrión sobre una fila: llamar, sentar, no vino y quitar.

    Con dos anfitriones a la vez la fila se bloquea: el segundo ve el estado ya cambiado, así que
    repetir la misma acción no hace nada y una acción imposible falla con el estado actual.
    """

    def __init__(
        self,
        entries: QueueEntryRepository,
        events: EntryEventRepository,
        uow: UnitOfWork,
        clock: Clock,
        publisher: RealtimePublisher,
    ):
        self._entries = entries
        self._events = events
        self._uow = uow
        self._clock = clock
        self._publisher = publisher

    async def execute(self, venue_id: int, user_id: int, entry_id: int, target: EntryStatus) -> QueueEntry:
        entry = await self._entries.get_for_update(entry_id)
        if entry is None or entry.venue_id != venue_id:
            raise NotFound("entry_not_found", "No encontramos esa entrada.")

        event = entry.transition(target, Actor.HOST, self._clock.now(), user_id=user_id)
        if event is not None:
            await self._entries.save(entry)
            event = await self._events.add(event)
        await self._uow.commit()
        if event is not None:
            await announce_entry_event(self._publisher, entry, event)
        return entry
