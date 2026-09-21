from datetime import timedelta

from app.auth.application.errors import InvalidToken
from app.auth.application.ports import AuthSessionRepository, UserRepository
from app.auth.application.views import AuthenticatedUser
from app.auth.domain.tokens import hash_token
from app.shared.application.ports import Clock, UnitOfWork

# Para no escribir en la base en cada petición, last_used_at solo se refresca pasado este intervalo.
TOUCH_INTERVAL = timedelta(minutes=1)


class AuthenticateUseCase:
    """Valida el token de una tablet. No hay caducidad por tiempo: solo cuenta que no esté revocado."""

    def __init__(self, users: UserRepository, sessions: AuthSessionRepository, uow: UnitOfWork, clock: Clock):
        self._users = users
        self._sessions = sessions
        self._uow = uow
        self._clock = clock

    async def execute(self, token: str) -> AuthenticatedUser:
        session = await self._sessions.get_by_token_hash(hash_token(token))
        if session is None or not session.is_active:
            raise InvalidToken()
        user = await self._users.get_by_id(session.user_id)
        if user is None or not user.is_active:
            raise InvalidToken()

        now = self._clock.now()
        if now - session.last_used_at >= TOUCH_INTERVAL:
            session.touch(now)
            await self._sessions.save(session)
            await self._uow.commit()
        return AuthenticatedUser(user.id, user.venue_id, user.username)
