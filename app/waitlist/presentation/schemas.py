from datetime import date, datetime

from pydantic import BaseModel, Field

from app.venues.presentation.schemas import HostVenueOut


class JoinIn(BaseModel):
    name: str = Field(max_length=200)
    phone: str = Field(max_length=40)  # con o sin prefijo; se normaliza según el país del local
    party_size: int
    consent: bool


class LookupIn(BaseModel):
    ticket: int = Field(ge=1, le=9_999_999)
    phone: str = Field(max_length=40)


class EtaOut(BaseModel):
    min: int
    max: int


class EntryVenueOut(BaseModel):
    slug: str
    name: str


class EntryOut(BaseModel):
    """Solo la información del propio comensal: nunca datos de otros."""

    token: str
    ticket: int
    name: str
    party_size: int
    phone_display: str  # +51 987 654 321
    status: str  # waiting | called | seated | cancelled | no_show | removed
    position: int | None  # solo esperando
    eta: EtaOut | None  # solo esperando
    hold_ends_at: datetime | None  # solo llamado
    on_the_way: bool
    venue: EntryVenueOut
    server_time: datetime


class JoinOut(EntryOut):
    already_in_queue: bool  # el teléfono ya tenía una entrada activa: es la misma, no se creó otra


class HostRowOut(BaseModel):
    id: int
    ticket: int
    name: str
    party_size: int
    phone_e164: str  # para el enlace tel:
    phone_display: str
    status: str  # waiting | called
    joined_at: datetime
    called_at: datetime | None
    hold_ends_at: datetime | None
    hold_expired: bool
    on_the_way: bool


class FinishedOut(BaseModel):
    seated: int
    left: int  # cancelaron o fueron sacados
    no_show: int


class HostQueueOut(BaseModel):
    venue: HostVenueOut
    waiting: int
    called: int
    rows: list[HostRowOut]  # esperando y llamados, por orden de llegada
    finished: FinishedOut  # de la jornada en curso
    service_date: date | None
    server_time: datetime
