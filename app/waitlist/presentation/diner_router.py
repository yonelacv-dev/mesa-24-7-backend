from collections.abc import Awaitable, Callable

from fastapi import APIRouter, Depends, Response, status
from fastapi.responses import StreamingResponse

from app.shared.application.ports import RealtimeSubscriber
from app.shared.dependencies import get_session_releaser, get_sse_heartbeat_seconds, get_subscriber, rate_limit
from app.shared.presentation.schemas import ERROR_RESPONSES
from app.shared.presentation.sse import SSE_HEADERS
from app.waitlist.application.use_cases.join_queue import JoinQueueCommand
from app.waitlist.application.use_cases.lookup_ticket import LookupTicketCommand
from app.waitlist.dependencies import (
    WaitlistServices,
    WaitlistServicesFactory,
    waitlist_services,
    waitlist_services_factory,
)
from app.waitlist.presentation.mappers import entry_out
from app.waitlist.presentation.schemas import EntryOut, JoinIn, JoinOut, LookupIn
from app.waitlist.presentation.streams import diner_stream

router = APIRouter(
    prefix="/venues/{slug}/diner",
    tags=["diner"],
    responses={k: ERROR_RESPONSES[k] for k in (404, 409, 422, 429)},
)

JOIN_LIMIT = (10, 60)  # por minuto y por IP
LOOKUP_LIMIT = (10, 60)


@router.post(
    "/join",
    response_model=JoinOut,
    status_code=status.HTTP_201_CREATED,
    summary="Unirse a la cola",
    description="201 si crea la entrada; 200 con `already_in_queue: true` si el teléfono ya estaba en la cola.",
    dependencies=[Depends(rate_limit("join", *JOIN_LIMIT))],
)
async def join(
    slug: str, body: JoinIn, response: Response, services: WaitlistServices = Depends(waitlist_services)
) -> JoinOut:
    result = await services.join_queue.execute(
        JoinQueueCommand(
            venue_slug=slug,
            name=body.name,
            phone=body.phone,
            party_size=body.party_size,
            consent_accepted=body.consent,
        )
    )
    if result.already_in_queue:
        response.status_code = status.HTTP_200_OK
    view = await services.get_entry_state.execute(result.entry.public_token, slug)
    return JoinOut(**entry_out(view).model_dump(), already_in_queue=result.already_in_queue)


@router.post(
    "/tickets/lookup",
    response_model=EntryOut,
    summary="Recuperar mi turno con ticket y teléfono",
    dependencies=[Depends(rate_limit("lookup", *LOOKUP_LIMIT))],
)
async def lookup_ticket(slug: str, body: LookupIn, services: WaitlistServices = Depends(waitlist_services)) -> EntryOut:
    view = await services.lookup_ticket.execute(LookupTicketCommand(slug, body.ticket, body.phone))
    return entry_out(view)


@router.get("/entries/{token}", response_model=EntryOut, summary="Mi turno")
async def get_entry(slug: str, token: str, services: WaitlistServices = Depends(waitlist_services)) -> EntryOut:
    return entry_out(await services.get_entry_state.execute(token, slug))


@router.post("/entries/{token}/cancel", response_model=EntryOut, summary="Ya no voy")
async def cancel(slug: str, token: str, services: WaitlistServices = Depends(waitlist_services)) -> EntryOut:
    return entry_out(await services.leave_queue.execute(token, slug))


@router.post(
    "/entries/{token}/on-the-way",
    response_model=EntryOut,
    summary="Voy en camino",
    description="Solo avisa al anfitrión: no cambia el estado ni extiende el plazo.",
)
async def on_the_way(slug: str, token: str, services: WaitlistServices = Depends(waitlist_services)) -> EntryOut:
    return entry_out(await services.notify_on_the_way.execute(token, slug))


@router.get(
    "/entries/{token}/stream",
    summary="Mi turno en vivo (SSE)",
    description="Evento `state` con el mismo cuerpo que `GET /entries/{token}`. Al reconectar llega todo el estado.",
    response_class=StreamingResponse,
)
async def stream_entry(
    slug: str,
    token: str,
    services: WaitlistServices = Depends(waitlist_services),
    stream_services: WaitlistServicesFactory = Depends(waitlist_services_factory),
    subscriber: RealtimeSubscriber = Depends(get_subscriber),
    heartbeat_seconds: float = Depends(get_sse_heartbeat_seconds),
    release_session: Callable[[], Awaitable[None]] = Depends(get_session_releaser),
) -> StreamingResponse:
    await services.get_entry_state.execute(token, slug)  # 404 antes de abrir el stream
    await release_session()
    return StreamingResponse(
        diner_stream(stream_services, subscriber, slug, token, heartbeat_seconds),
        media_type="text/event-stream",
        headers=SSE_HEADERS,
    )
