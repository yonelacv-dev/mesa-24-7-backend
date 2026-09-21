from __future__ import annotations

from datetime import datetime, time

from sqlalchemy import BigInteger, Boolean, CheckConstraint, ForeignKey, String, Time, UniqueConstraint, text
from sqlalchemy.dialects.mysql import TINYINT
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.shared.infrastructure.types import UTC_NOW_SQL, UtcDateTime, utc_now


class VenueModel(Base):
    __tablename__ = "venue"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    slug: Mapped[str] = mapped_column(String(80), unique=True)
    name: Mapped[str] = mapped_column(String(120))
    country_code: Mapped[str] = mapped_column(String(2))
    timezone: Mapped[str] = mapped_column(String(64))
    minutes_per_position: Mapped[int] = mapped_column(TINYINT(unsigned=True), server_default=text("4"))
    hold_minutes: Mapped[int] = mapped_column(TINYINT(unsigned=True), server_default=text("10"))
    paused: Mapped[bool] = mapped_column(Boolean, server_default=text("0"))
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, default=utc_now, server_default=UTC_NOW_SQL)
    updated_at: Mapped[datetime] = mapped_column(
        UtcDateTime, default=utc_now, onupdate=utc_now, server_default=UTC_NOW_SQL
    )

    schedule: Mapped[list[VenueScheduleModel]] = relationship(
        order_by="VenueScheduleModel.weekday", cascade="all, delete-orphan", lazy="selectin"
    )


class VenueScheduleModel(Base):
    __tablename__ = "venue_schedule"
    __table_args__ = (
        UniqueConstraint("venue_id", "weekday", name="uq_venue_schedule_venue_weekday"),
        CheckConstraint("weekday BETWEEN 0 AND 6", name="weekday_range"),
        CheckConstraint("NOT is_open OR start_time <> end_time", name="start_differs_from_end_when_open"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    venue_id: Mapped[int] = mapped_column(ForeignKey("venue.id", ondelete="CASCADE"))
    weekday: Mapped[int] = mapped_column(TINYINT(unsigned=True))  # 0 = lunes ... 6 = domingo
    is_open: Mapped[bool] = mapped_column(Boolean)
    start_time: Mapped[time] = mapped_column(Time)  # hora local del local
    end_time: Mapped[time] = mapped_column(Time)
