from datetime import UTC, datetime

from sqlalchemy import text
from sqlalchemy.dialects.mysql import DATETIME
from sqlalchemy.types import TypeDecorator


class UtcDateTime(TypeDecorator):
    """DATETIME(6) que guarda siempre UTC y devuelve datetimes con zona horaria UTC.

    Rechaza datetimes naive: si algo no sabe en qué zona está, que falle en vez de guardar una hora ambigua.
    """

    impl = DATETIME(fsp=6)
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError("Se esperaba un datetime con zona horaria (UTC).")
        return value.astimezone(UTC).replace(tzinfo=None)

    def process_result_value(self, value: datetime | None, dialect) -> datetime | None:
        return None if value is None else value.replace(tzinfo=UTC)


def utc_now() -> datetime:
    return datetime.now(UTC)


# Valor por defecto del servidor en UTC, sea cual sea la zona horaria de la sesión de MySQL.
UTC_NOW_SQL = text("(UTC_TIMESTAMP(6))")
