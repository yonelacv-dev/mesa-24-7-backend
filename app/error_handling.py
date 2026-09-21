"""Traduce errores del dominio y de la aplicación a respuestas HTTP con un único formato."""

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.shared.application.errors import ApplicationError, Forbidden, NotFound, RateLimited, Unauthorized
from app.shared.domain.errors import DomainError, ValidationFailed
from app.venues.domain.errors import ListClosed, ListPaused
from app.waitlist.domain.errors import ActorNotAllowed, InvalidTransition

logger = logging.getLogger(__name__)

STATUS_BY_ERROR: dict[type[Exception], int] = {
    ValidationFailed: 422,
    ListClosed: 409,
    ListPaused: 409,
    InvalidTransition: 409,
    ActorNotAllowed: 403,
    NotFound: 404,
    Unauthorized: 401,
    Forbidden: 403,
    RateLimited: 429,
}


def error_body(code: str, message: str, field: str | None = None) -> dict:
    return {"error": {"code": code, "message": message, "field": field}}


def status_for(error: Exception) -> int:
    for klass in type(error).__mro__:
        if klass in STATUS_BY_ERROR:
            return STATUS_BY_ERROR[klass]
    return 500


def register_exception_handlers(app: FastAPI) -> None:
    async def handle_domain(request: Request, error: DomainError) -> JSONResponse:
        return JSONResponse(status_code=status_for(error), content=error_body(error.code, error.message, error.field))

    async def handle_application(request: Request, error: ApplicationError) -> JSONResponse:
        headers = {}
        if isinstance(error, RateLimited):
            headers["Retry-After"] = str(error.retry_after)
        if isinstance(error, Unauthorized):
            headers["WWW-Authenticate"] = "Bearer"
        return JSONResponse(
            status_code=status_for(error), content=error_body(error.code, error.message), headers=headers
        )

    async def handle_request_validation(request: Request, error: RequestValidationError) -> JSONResponse:
        first = error.errors()[0]
        location = [str(part) for part in first["loc"] if part not in ("body", "query", "path")]
        return JSONResponse(
            status_code=422,
            content=error_body("validation_error", "Los datos enviados no son válidos.", ".".join(location) or None),
        )

    async def handle_unexpected(request: Request, error: Exception) -> JSONResponse:
        logger.exception("Error no controlado en %s %s", request.method, request.url.path)
        return JSONResponse(status_code=500, content=error_body("internal_error", "Ocurrió un error inesperado."))

    app.add_exception_handler(DomainError, handle_domain)
    app.add_exception_handler(ApplicationError, handle_application)
    app.add_exception_handler(RequestValidationError, handle_request_validation)
    app.add_exception_handler(Exception, handle_unexpected)
