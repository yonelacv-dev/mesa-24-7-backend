from __future__ import annotations

from datetime import datetime

from sqlalchemy import CHAR, BigInteger, Boolean, ForeignKey, String, text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.shared.infrastructure.types import UTC_NOW_SQL, UtcDateTime, utc_now


class UserModel(Base):
    __tablename__ = "user"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    venue_id: Mapped[int] = mapped_column(ForeignKey("venue.id"))
    username: Mapped[str] = mapped_column(String(64), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, server_default=text("1"))
    last_login_at: Mapped[datetime | None] = mapped_column(UtcDateTime)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, default=utc_now, server_default=UTC_NOW_SQL)
    updated_at: Mapped[datetime] = mapped_column(
        UtcDateTime, default=utc_now, onupdate=utc_now, server_default=UTC_NOW_SQL
    )


class AuthModel(Base):
    """Sesión de una tablet. Sin expires_at: solo deja de valer si se revoca."""

    __tablename__ = "auth"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("user.id", ondelete="CASCADE"))
    token_hash: Mapped[str] = mapped_column(CHAR(64), unique=True)
    device_label: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(UtcDateTime)
    last_used_at: Mapped[datetime] = mapped_column(UtcDateTime)
    revoked_at: Mapped[datetime | None] = mapped_column(UtcDateTime)
