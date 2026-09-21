from pydantic import BaseModel


class ErrorBody(BaseModel):
    code: str
    message: str
    field: str | None = None


class ErrorResponse(BaseModel):
    error: ErrorBody


ERROR_RESPONSES = {
    401: {"model": ErrorResponse, "description": "Sesión o credenciales inválidas"},
    403: {"model": ErrorResponse, "description": "Sin permiso"},
    404: {"model": ErrorResponse, "description": "No existe"},
    409: {"model": ErrorResponse, "description": "Estado incompatible con la acción"},
    422: {"model": ErrorResponse, "description": "Datos inválidos"},
    429: {"model": ErrorResponse, "description": "Demasiados intentos"},
}
