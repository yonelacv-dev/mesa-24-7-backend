from fastapi import APIRouter, Depends

from app.shared.presentation.schemas import ERROR_RESPONSES
from app.venues.application.views import VenueStatusView
from app.venues.dependencies import HostContext, VenueServices, host_context, venue_services
from app.venues.domain.schedule import DayWindow
from app.venues.presentation.mappers import host_venue_out
from app.venues.presentation.schemas import HostVenueOut, ScheduleIn

router = APIRouter(
    prefix="/venues/{slug}/host",
    tags=["host"],
    responses={k: ERROR_RESPONSES[k] for k in (401, 403, 422)},
)


def _out(view: VenueStatusView) -> HostVenueOut:
    return host_venue_out(view.venue, view.status)


@router.post("/pause", response_model=HostVenueOut, summary="Pausar la lista (no entra nadie nuevo)")
async def pause(ctx: HostContext = Depends(host_context), services: VenueServices = Depends(venue_services)):
    return _out(await services.set_paused.execute(ctx.venue_id, True))


@router.post("/resume", response_model=HostVenueOut, summary="Reanudar la lista")
async def resume(ctx: HostContext = Depends(host_context), services: VenueServices = Depends(venue_services)):
    return _out(await services.set_paused.execute(ctx.venue_id, False))


@router.put("/schedule", response_model=HostVenueOut, summary="Guardar el horario de la semana")
async def update_schedule(
    body: ScheduleIn,
    ctx: HostContext = Depends(host_context),
    services: VenueServices = Depends(venue_services),
):
    windows = [DayWindow(day.is_open, day.start, day.end) for day in body.days]
    return _out(await services.update_schedule.execute(ctx.venue_id, windows))
