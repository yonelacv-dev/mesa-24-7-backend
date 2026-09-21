from fastapi import APIRouter, Depends

from app.shared.presentation.schemas import ERROR_RESPONSES
from app.venues.dependencies import VenueServices, venue_services
from app.venues.presentation.mappers import venue_status_out
from app.venues.presentation.schemas import VenueStatusOut

router = APIRouter(prefix="/venues/{slug}/diner", tags=["diner"], responses={404: ERROR_RESPONSES[404]})


@router.get("/status", response_model=VenueStatusOut, summary="Estado de la lista de espera del local")
async def venue_status(slug: str, services: VenueServices = Depends(venue_services)) -> VenueStatusOut:
    return venue_status_out(await services.get_status.execute(slug))
