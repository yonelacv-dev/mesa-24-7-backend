from app.auth.application.ports import AuthSessionRepository
from app.auth.domain.tokens import hash_token
from app.shared.application.ports import Clock, UnitOfWork


class LogoutUseCase:
    """Cierra solo la sesión de esta tablet; las demás del mismo usuario siguen vigentes."""

    def __init__(self, sessions: AuthSessionRepository, uow: UnitOfWork, clock: Clock):
        self._sessions = sessions
        self._uow = uow
        self._clock = clock

    async def execute(self, token: str) -> None:
        session = await self._sessions.get_by_token_hash(hash_token(token))
        if session is None or not session.is_active:
            return
        session.revoke(self._clock.now())
        await self._sessions.save(session)
        await self._uow.commit()
