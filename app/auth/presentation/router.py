from fastapi import APIRouter, Depends, Response, status

from app.auth.application.views import AuthenticatedUser
from app.auth.dependencies import AuthServices, auth_services, bearer_token, current_user
from app.auth.presentation.schemas import LoginIn, LoginOut, SessionUserOut, SessionVenueOut
from app.shared.application.errors import RateLimited
from app.shared.application.ports import RateLimiter
from app.shared.dependencies import get_rate_limiter, rate_limit
from app.shared.presentation.schemas import ERROR_RESPONSES
from app.venues.dependencies import VenueServices, venue_services

router = APIRouter(prefix="/auth", tags=["auth"], responses={k: ERROR_RESPONSES[k] for k in (401, 429)})

LOGIN_PER_IP = (20, 60)  # intentos por minuto y por IP
LOGIN_PER_USERNAME = (5, 60)  # intentos por minuto y por usuario, contra fuerza bruta distribuida


async def _session_user(user: AuthenticatedUser, venues: VenueServices) -> SessionUserOut:
    venue = await venues.get_venue.execute(user.venue_id)
    return SessionUserOut(
        id=user.user_id, username=user.username, venue=SessionVenueOut(slug=venue.slug, name=venue.name)
    )


@router.post(
    "/login",
    response_model=LoginOut,
    summary="Iniciar sesión (tablet del anfitrión)",
    dependencies=[Depends(rate_limit("login", *LOGIN_PER_IP))],
)
async def login(
    body: LoginIn,
    services: AuthServices = Depends(auth_services),
    venues: VenueServices = Depends(venue_services),
    limiter: RateLimiter = Depends(get_rate_limiter),
) -> LoginOut:
    retry_after = limiter.hit(f"login-user:{body.username.strip().lower()}", *LOGIN_PER_USERNAME)
    if retry_after is not None:
        raise RateLimited(retry_after)
    result = await services.login.execute(body.username, body.password)
    return LoginOut(token=result.token, user=await _session_user(result.user, venues))


@router.get("/me", response_model=SessionUserOut, summary="Usuario y local de la sesión actual")
async def me(
    user: AuthenticatedUser = Depends(current_user), venues: VenueServices = Depends(venue_services)
) -> SessionUserOut:
    return await _session_user(user, venues)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT, summary="Cerrar la sesión de esta tablet")
async def logout(token: str = Depends(bearer_token), services: AuthServices = Depends(auth_services)) -> Response:
    await services.logout.execute(token)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
