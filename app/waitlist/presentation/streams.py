"""Generadores SSE. Cada refresco abre una sesión corta: la de la petición no puede vivir lo que dura el stream."""

import asyncio
from collections.abc import AsyncIterator

from app.shared.application.ports import RealtimeSubscriber
from app.shared.presentation.sse import sse_heartbeat, sse_message
from app.venues.application.realtime import QUEUE_CHANGED, host_topic, venue_topic
from app.waitlist.dependencies import WaitlistServicesFactory
from app.waitlist.presentation.mappers import entry_out, host_queue_out

# Cada cuántos latidos se reenvía el estado completo aunque nadie haya publicado nada: cubre lo que cambia
# solo con el tiempo (el cierre del horario) y cualquier evento perdido.
REFRESH_EVERY_N_HEARTBEATS = 2


async def diner_stream(
    services: WaitlistServicesFactory,
    subscriber: RealtimeSubscriber,
    slug: str,
    token: str,
    heartbeat_seconds: float,
) -> AsyncIterator[str]:
    """Mi turno en vivo. Emite `state` (el mismo cuerpo que GET /entries/{token}); solo datos del propio comensal."""

    async def load():
        async with services.open() as s:
            return await s.get_entry_state.execute(token, slug)

    venue_id = (await load()).venue.id
    async with subscriber.subscribe(venue_topic(venue_id)) as queue:
        # Se lee DESPUÉS de suscribirse: nada de lo publicado entre la lectura y la suscripción se pierde.
        yield sse_message("state", entry_out(await load()).model_dump(mode="json"))
        beats = 0
        while True:
            try:
                await asyncio.wait_for(queue.get(), timeout=heartbeat_seconds)
                while not queue.empty():  # varias señales seguidas valen por una: se lee el estado una vez
                    queue.get_nowait()
            except TimeoutError:
                beats += 1
                if beats % REFRESH_EVERY_N_HEARTBEATS:
                    yield sse_heartbeat()
                    continue
            yield sse_message("state", entry_out(await load()).model_dump(mode="json"))


async def host_stream(
    services: WaitlistServicesFactory,
    subscriber: RealtimeSubscriber,
    venue_id: int,
    heartbeat_seconds: float,
) -> AsyncIterator[str]:
    """La tablet en vivo: `queue` (la cola completa) y `feed` (qué acaba de pasar, para los avisos)."""

    async def load():
        async with services.open() as s:
            return host_queue_out(await s.host_queue.execute(venue_id)).model_dump(mode="json")

    async with subscriber.subscribe(venue_topic(venue_id), host_topic(venue_id)) as queue:
        yield sse_message("queue", await load())
        beats = 0
        while True:
            try:
                events = [await asyncio.wait_for(queue.get(), timeout=heartbeat_seconds)]
                while not queue.empty():
                    events.append(queue.get_nowait())
            except TimeoutError:
                beats += 1
                if beats % REFRESH_EVERY_N_HEARTBEATS:
                    yield sse_heartbeat()
                    continue
                events = []  # refresco periódico: solo reenvía la cola
            for event in events:
                if event.kind != QUEUE_CHANGED:
                    yield sse_message("feed", {"kind": event.kind, **event.data})
            yield sse_message("queue", await load())
