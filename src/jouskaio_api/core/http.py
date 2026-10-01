"""HTTP plumbing shared by every module: request ids, error translation, error docs."""

import logging
import re
import uuid
from typing import Any

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

from jouskaio_api.core.errors import (
    AuthenticationError,
    ConflictError,
    DomainError,
    ExternalServiceError,
    NotFoundError,
)
from jouskaio_api.core.logging_setup import request_id_var

logger = logging.getLogger(__name__)

_SAFE_REQUEST_ID = re.compile(r"^[A-Za-z0-9-]{1,64}$")

# Most specific first: the first matching type wins. Any other DomainError is a 400.
_STATUS_BY_ERROR: tuple[tuple[type[DomainError], int], ...] = (
    (AuthenticationError, 401),
    (NotFoundError, 404),
    (ConflictError, 409),
    (ExternalServiceError, 502),
)


class ErrorResponse(BaseModel):
    """Body of every error returned by the API (request validation errors excepted: 422)."""

    error: str = Field(
        description="Error type, stable and machine-readable.", examples=["NotFoundError"]
    )
    detail: str = Field(
        description="Human-readable explanation.", examples=["Job 3f2a9c not found"]
    )


ERROR_DESCRIPTIONS: dict[int, str] = {
    400: "The request is invalid for a business reason.",
    401: "The Bearer token is missing or wrong.",
    404: "The resource does not exist.",
    409: "The request conflicts with the current state of the resource.",
    500: "Unexpected server error. The request id in `X-Request-ID` locates it in the logs.",
    502: "A dependency (external tool, file system, remote service) failed.",
}


def error_responses(*codes: int, **descriptions: str) -> dict[int | str, dict[str, Any]]:
    """OpenAPI ``responses`` entries for the given error codes.

    A description can be overridden per code with keyword arguments named ``e<code>``,
    for example ``error_responses(409, e409="A run is already in progress.")``.
    """
    return {
        code: {
            "model": ErrorResponse,
            "description": descriptions.get(f"e{code}", ERROR_DESCRIPTIONS[code]),
        }
        for code in codes
    }


class RequestIdMiddleware(BaseHTTPMiddleware):
    """Propagate (or create) an ``X-Request-ID`` and expose it to the logs."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        incoming = request.headers.get("X-Request-ID", "")
        request_id = incoming if _SAFE_REQUEST_ID.match(incoming) else uuid.uuid4().hex
        token = request_id_var.set(request_id)
        try:
            response = await call_next(request)
        finally:
            request_id_var.reset(token)
        response.headers["X-Request-ID"] = request_id
        return response


def _error(status_code: int, error: str, detail: str) -> JSONResponse:
    body = ErrorResponse(error=error, detail=detail)
    headers = {"WWW-Authenticate": "Bearer"} if status_code == 401 else None
    return JSONResponse(status_code=status_code, content=body.model_dump(), headers=headers)


async def _handle_domain_error(request: Request, exc: Exception) -> JSONResponse:
    status_code = next((code for kind, code in _STATUS_BY_ERROR if isinstance(exc, kind)), 400)
    return _error(status_code, type(exc).__name__, str(exc))


async def _handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("unhandled error on %s %s", request.method, request.url.path)
    # Never echo the exception: it may hold internal details (paths, hosts, values).
    return _error(500, "InternalServerError", "Unexpected error, see the server logs")


def register_http_layer(app: FastAPI) -> None:
    app.add_middleware(RequestIdMiddleware)
    app.add_exception_handler(DomainError, _handle_domain_error)
    app.add_exception_handler(Exception, _handle_unexpected_error)
