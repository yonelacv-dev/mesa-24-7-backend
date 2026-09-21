from abc import ABC, abstractmethod

from app.auth.domain.entities import AuthSession, User


class UserRepository(ABC):
    @abstractmethod
    async def get_by_id(self, user_id: int) -> User | None: ...

    @abstractmethod
    async def get_by_username(self, username: str) -> User | None: ...

    @abstractmethod
    async def save(self, user: User) -> None: ...


class AuthSessionRepository(ABC):
    @abstractmethod
    async def add(self, session: AuthSession) -> AuthSession: ...

    @abstractmethod
    async def get_by_token_hash(self, token_hash: str) -> AuthSession | None: ...

    @abstractmethod
    async def save(self, session: AuthSession) -> None: ...


class PasswordHasher(ABC):
    """Asíncrono porque argon2/bcrypt son costosos y no deben bloquear el event loop."""

    @abstractmethod
    async def hash(self, password: str) -> str: ...

    @abstractmethod
    async def verify(self, password_hash: str, password: str) -> bool: ...

    @abstractmethod
    async def burn(self, password: str) -> None:
        """Gasta el mismo tiempo que una verificación real, para no revelar qué usuarios existen."""
