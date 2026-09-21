from dataclasses import dataclass
from datetime import datetime


@dataclass
class User:
    venue_id: int
    username: str
    password_hash: str
    is_active: bool = True
    last_login_at: datetime | None = None
    id: int | None = None


@dataclass
class AuthSession:
    """Sesión de una tablet. No vence por tiempo y no invalida a otras del mismo usuario (decisión del piloto)."""

    user_id: int
    token_hash: str
    created_at: datetime
    last_used_at: datetime
    device_label: str | None = None
    revoked_at: datetime | None = None
    id: int | None = None

    @property
    def is_active(self) -> bool:
        return self.revoked_at is None

    def touch(self, now: datetime) -> None:
        self.last_used_at = now

    def revoke(self, now: datetime) -> None:
        if self.revoked_at is None:
            self.revoked_at = now
