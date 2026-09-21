from datetime import datetime, time

from pydantic import BaseModel, Field


class NextOpenOut(BaseModel):
    day_offset: int  # 0 = hoy, 1 = mañana, ...
    weekday: int  # 0 = lunes ... 6 = domingo
    time: str  # HH:MM, hora local del local


class ListStatusOut(BaseModel):
    kind: str  # open | paused | closed
    closes_at: str | None  # HH:MM, solo si está dentro de horario
    next_open: NextOpenOut | None  # solo si está cerrada; None si el local no tiene ningún día abierto


class VenueOut(BaseModel):
    slug: str
    name: str
    country_code: str
    phone_prefix: str  # +51


class VenueStatusOut(BaseModel):
    """Lo que ve el comensal antes de unirse."""

    venue: VenueOut
    status: ListStatusOut
    server_time: datetime


class DayWindowOut(BaseModel):
    weekday: int  # 0 = lunes ... 6 = domingo
    is_open: bool
    start: str
    end: str
    crosses_midnight: bool


class HostVenueOut(BaseModel):
    """El local visto por su anfitrión: incluye horario y ajustes."""

    slug: str
    name: str
    country_code: str
    phone_prefix: str
    timezone: str
    paused: bool
    hold_minutes: int
    minutes_per_position: int
    list_status: ListStatusOut
    schedule: list[DayWindowOut]


class DayWindowIn(BaseModel):
    is_open: bool
    start: time
    end: time


class ScheduleIn(BaseModel):
    """Los 7 días en orden: el primero es lunes y el último domingo."""

    days: list[DayWindowIn] = Field(min_length=7, max_length=7)
