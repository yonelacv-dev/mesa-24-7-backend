class ApplicationError(Exception):
    """Errores de orquestación (no son reglas del dominio). `code` es estable para el front."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


class NotFound(ApplicationError):
    pass


class Unauthorized(ApplicationError):
    pass


class Forbidden(ApplicationError):
    pass


class RateLimited(ApplicationError):
    def __init__(self, retry_after: int):
        super().__init__("rate_limited", "Demasiados intentos. Espera un momento e inténtalo de nuevo.")
        self.retry_after = retry_after
