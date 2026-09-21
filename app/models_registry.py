"""Importa todos los modelos ORM para que Base.metadata los conozca (Alembic y los tests de integración)."""

from app.auth.infrastructure import models as auth_models  # noqa: F401
from app.venues.infrastructure import models as venue_models  # noqa: F401
from app.waitlist.infrastructure import models as waitlist_models  # noqa: F401
