from collections.abc import Awaitable, Callable

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from app.shared.application.ports import RealtimeSubscriber
from app.shared.dependencies import get_session_releaser, get_sse_heartbeat_seconds, get_subscriber
from app.shared.presentation.schemas import ERROR_RESPONSES
from app.shared.presentation.sse import SSE_HEADERS
from app.venues.dependencies import HostContext, host_context
from app.waitlist.dependencies import (
    WaitlistServices,
    WaitlistServicesFactory,
    waitlist_services,
    waitlist_services_factory,
)
from app.waitlist.domain.enums import EntryStatus
from app.waitlist.presentation.mappers import host_queue_out
from app.waitlist.presentation.schemas import HostQueueOut
from app.waitlist.presentation.streams import host_stream

router = APIRouter(
    prefix="/venues/{slug}/host",
    tags=["host"],
    responses={k: ERROR_RESPONSES[k] for k in (401, 403, 404, 409)},
)


async def _queue(services: WaitlistServices, ctx: HostContext) -> HostQueueOut:
    return host_queue_out(await services.host_queue.execute(ctx.venue_id))


@router.get("/queue", response_model=HostQueueOut, summary="La cola del local")
async def get_queue(
    ctx: HostContext = Depends(host_context), services: WaitlistServices = Depends(waitlist_services)
) -> HostQueueOut:
    return await _queue(services, ctx)


def _action(path: str, target: EntryStatus, summary: str) -> None:
    """Las cuatro acciones sobre una fila son idénticas salvo el estado destino. Todas devuelven la cola actualizada."""

    async def endpoint(
        entry_id: int,
        ctx: HostContext = Depends(host_context),
        services: WaitlistServices = Depends(waitlist_services),
    ) -> HostQueueOut:
        await services.change_status.execute(ctx.venue_id, ctx.user.user_id, entry_id, target)
        return await _queue(services, ctx)

    endpoint.__name__ = f"{target.value}_entry"
    router.add_api_route(
        f"/entries/{{entry_id}}/{path}",
        endpoint,
        methods=["POST"],
        response_model=HostQueueOut,
        summary=summary,
        description="Repetir la acción no tiene efecto doble (200). Si el estado ya no lo permite: 409.",
    )


_action("call", EntryStatus.CALLED, "Llamar")
_action("seat", EntryStatus.SEATED, "Sentar")
_action("no-show", EntryStatus.NO_SHOW, "No vino")
_action("remove", EntryStatus.REMOVED, "Quitar de la lista")


@router.get(
    "/stream",
    summary="La cola en vivo (SSE)",
    description=(
        "Eventos `queue` (la cola completa, igual a `GET /queue`) y `feed` (qué acaba de pasar). "
        "`EventSource` no permite el header Authorization: usar `fetch` con streaming."
    ),
    response_class=StreamingResponse,
)
async def stream_queue(
    ctx: HostContext = Depends(host_context),
    stream_services: WaitlistServicesFactory = Depends(waitlist_services_factory),
    subscriber: RealtimeSubscriber = Depends(get_subscriber),
    heartbeat_seconds: float = Depends(get_sse_heartbeat_seconds),
    release_session: Callable[[], Awaitable[None]] = Depends(get_session_releaser),
) -> StreamingResponse:
    await release_session()  # la autenticación ya usó la sesión de la petición: no retenerla durante el stream
    return StreamingResponse(
        host_stream(stream_services, subscriber, ctx.venue_id, heartbeat_seconds),
        media_type="text/event-stream",
        headers=SSE_HEADERS,
    )
