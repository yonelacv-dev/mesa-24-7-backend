"""Raíz de composición de auth: arma los casos de uso con sus adaptadores y expone al usuario autenticado."""

from functools import lru_cache

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.application.errors import InvalidToken
from app.auth.application.use_cases.authenticate import AuthenticateUseCase
from app.auth.application.use_cases.login import LoginUseCase
from app.auth.application.use_cases.logout import LogoutUseCase
from app.auth.application.views import AuthenticatedUser
from app.auth.infrastructure.argon2_hasher import Argon2PasswordHasher
from app.auth.infrastructure.repositories import SQLAlchemyAuthSessionRepository, SQLAlchemyUserRepository
from app.database import get_session
from app.shared.application.ports import Clock, TokenGenerator
from app.shared.dependencies import get_clock, get_tokens
from app.shared.infrastructure.unit_of_work import SQLAlchemyUnitOfWork


@lru_cache
def get_hasher() -> Argon2PasswordHasher:
    return Argon2PasswordHasher()


class AuthServices:
    def __init__(self, session: AsyncSession, clock: Clock, tokens: TokenGenerator):
        self._uow = SQLAlchemyUnitOfWork(session)
        self._users = SQLAlchemyUserRepository(session)
        self._sessions = SQLAlchemyAuthSessionRepository(session)
        self._clock = clock
        self._tokens = tokens

    @property
    def login(self) -> LoginUseCase:
        return LoginUseCase(self._users, self._sessions, get_hasher(), self._tokens, self._uow, self._clock)

    @property
    def authenticate(self) -> AuthenticateUseCase:
        return AuthenticateUseCase(self._users, self._sessions, self._uow, self._clock)

    @property
    def logout(self) -> LogoutUseCase:
        return LogoutUseCase(self._sessions, self._uow, self._clock)


def auth_services(
    session: AsyncSession = Depends(get_session),
    clock: Clock = Depends(get_clock),
    tokens: TokenGenerator = Depends(get_tokens),
) -> AuthServices:
    return AuthServices(session, clock, tokens)


_bearer = HTTPBearer(auto_error=False, description="Token devuelto por POST /auth/login")


async def bearer_token(credentials: HTTPAuthorizationCredentials | None = Depends(_bearer)) -> str:
    if credentials is None:
        raise InvalidToken()
    return credentials.credentials


async def current_user(
    token: str = Depends(bearer_token), services: AuthServices = Depends(auth_services)
) -> AuthenticatedUser:
    return await services.authenticate.execute(token)
