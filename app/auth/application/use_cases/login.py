from app.auth.application.errors import InvalidCredentials
from app.auth.application.ports import AuthSessionRepository, PasswordHasher, UserRepository
from app.auth.application.views import AuthenticatedUser, LoginResult
from app.auth.domain.entities import AuthSession
from app.auth.domain.tokens import hash_token
from app.shared.application.ports import Clock, TokenGenerator, UnitOfWork


class LoginUseCase:
    """Cada login abre una sesión nueva: dos tablets pueden usar la misma cuenta a la vez."""

    def __init__(
        self,
        users: UserRepository,
        sessions: AuthSessionRepository,
        hasher: PasswordHasher,
        tokens: TokenGenerator,
        uow: UnitOfWork,
        clock: Clock,
    ):
        self._users = users
        self._sessions = sessions
        self._hasher = hasher
        self._tokens = tokens
        self._uow = uow
        self._clock = clock

    async def execute(self, username: str, password: str, device_label: str | None = None) -> LoginResult:
        user = await self._users.get_by_username(username.strip())
        if user is None:
            await self._hasher.burn(password)
            raise InvalidCredentials()
        if not await self._hasher.verify(user.password_hash, password) or not user.is_active:
            raise InvalidCredentials()

        now = self._clock.now()
        token = self._tokens.new_token()
        await self._sessions.add(
            AuthSession(
                user_id=user.id,
                token_hash=hash_token(token),
                created_at=now,
                last_used_at=now,
                device_label=device_label[:255] if device_label else None,
            )
        )
        user.last_login_at = now
        await self._users.save(user)
        await self._uow.commit()
        return LoginResult(token=token, user=AuthenticatedUser(user.id, user.venue_id, user.username))
