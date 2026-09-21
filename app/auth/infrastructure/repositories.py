from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.application.ports import AuthSessionRepository, UserRepository
from app.auth.domain.entities import AuthSession, User
from app.auth.infrastructure.models import AuthModel, UserModel


def _user_to_domain(model: UserModel) -> User:
    return User(
        id=model.id,
        venue_id=model.venue_id,
        username=model.username,
        password_hash=model.password_hash,
        is_active=model.is_active,
        last_login_at=model.last_login_at,
    )


def _session_to_domain(model: AuthModel) -> AuthSession:
    return AuthSession(
        id=model.id,
        user_id=model.user_id,
        token_hash=model.token_hash,
        device_label=model.device_label,
        created_at=model.created_at,
        last_used_at=model.last_used_at,
        revoked_at=model.revoked_at,
    )


class SQLAlchemyUserRepository(UserRepository):
    def __init__(self, session: AsyncSession):
        self._session = session

    async def get_by_id(self, user_id: int) -> User | None:
        model = await self._session.get(UserModel, user_id)
        return _user_to_domain(model) if model else None

    async def get_by_username(self, username: str) -> User | None:
        model = await self._session.scalar(select(UserModel).where(UserModel.username == username))
        return _user_to_domain(model) if model else None

    async def save(self, user: User) -> None:
        model = await self._session.get(UserModel, user.id) if user.id else None
        if model is None:
            model = UserModel(venue_id=user.venue_id, username=user.username)
            self._session.add(model)
        model.password_hash = user.password_hash
        model.is_active = user.is_active
        model.last_login_at = user.last_login_at
        await self._session.flush()
        user.id = model.id


class SQLAlchemyAuthSessionRepository(AuthSessionRepository):
    def __init__(self, session: AsyncSession):
        self._session = session

    async def add(self, session: AuthSession) -> AuthSession:
        model = AuthModel(
            user_id=session.user_id,
            token_hash=session.token_hash,
            device_label=session.device_label,
            created_at=session.created_at,
            last_used_at=session.last_used_at,
            revoked_at=session.revoked_at,
        )
        self._session.add(model)
        await self._session.flush()
        session.id = model.id
        return session

    async def get_by_token_hash(self, token_hash: str) -> AuthSession | None:
        model = await self._session.scalar(select(AuthModel).where(AuthModel.token_hash == token_hash))
        return _session_to_domain(model) if model else None

    async def save(self, session: AuthSession) -> None:
        model = await self._session.get(AuthModel, session.id)
        model.last_used_at = session.last_used_at
        model.revoked_at = session.revoked_at
        await self._session.flush()
