class DomainError(Exception):
    """Base de las reglas de negocio violadas. `code` es estable para que el front elija el texto."""

    def __init__(self, code: str, message: str, *, field: str | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.field = field


class ValidationFailed(DomainError):
    pass
