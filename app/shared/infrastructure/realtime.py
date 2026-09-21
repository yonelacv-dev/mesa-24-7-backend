import asyncio
from collections import defaultdict
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from app.shared.application.ports import RealtimeEvent, RealtimePublisher, RealtimeSubscriber

QUEUE_SIZE = 100


class InMemoryRealtimeBroker(RealtimePublisher, RealtimeSubscriber):
    """Bus pub/sub en memoria del proceso: suficiente para un solo worker (el piloto).

    Con varios workers hay que cambiarlo por Redis u otro bus compartido; el puerto no cambia.
    """

    def __init__(self) -> None:
        self._subscribers: dict[str, set[asyncio.Queue[RealtimeEvent]]] = defaultdict(set)

    async def publish(self, topic: str, event: RealtimeEvent) -> None:
        for queue in list(self._subscribers.get(topic, ())):
            if queue.full():
                # Un cliente lento no frena a los demás. Los eventos son señales de "recarga", perder el
                # más viejo es inocuo porque el siguiente trae el estado completo.
                queue.get_nowait()
            queue.put_nowait(event)

    @asynccontextmanager
    async def subscribe(self, *topics: str) -> AsyncIterator[asyncio.Queue[RealtimeEvent]]:
        """Una sola cola recibe los eventos de todos los tópicos indicados."""
        queue: asyncio.Queue[RealtimeEvent] = asyncio.Queue(maxsize=QUEUE_SIZE)
        for topic in topics:
            self._subscribers[topic].add(queue)
        try:
            yield queue
        finally:
            for topic in topics:
                self._subscribers[topic].discard(queue)
                if not self._subscribers[topic]:
                    del self._subscribers[topic]

    def subscriber_count(self, topic: str) -> int:
        return len(self._subscribers.get(topic, ()))
