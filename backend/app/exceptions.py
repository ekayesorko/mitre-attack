"""Central exception handlers for consistent API error responses."""
import logging
from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.schemas.errors import ErrorDetail, ValidationErrorItem

logger = logging.getLogger(__name__)

# Map status codes to error codes for clients
STATUS_TO_ERROR_CODE = {
    status.HTTP_400_BAD_REQUEST: "bad_request",
    status.HTTP_401_UNAUTHORIZED: "unauthorized",
    status.HTTP_403_FORBIDDEN: "forbidden",
    status.HTTP_404_NOT_FOUND: "not_found",
    status.HTTP_409_CONFLICT: "conflict",
    status.HTTP_422_UNPROCESSABLE_ENTITY: "validation_error",
    status.HTTP_503_SERVICE_UNAVAILABLE: "service_unavailable",
}


def _error_code(status_code: int) -> str:
    return STATUS_TO_ERROR_CODE.get(status_code, "error")


async def http_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Handle FastAPI HTTPException with consistent JSON body."""
    from fastapi import HTTPException

    if not isinstance(exc, HTTPException):
        raise exc
    status_code = exc.status_code
    detail = exc.detail
    if isinstance(detail, list):
        # Some code may pass list (e.g. validation-style); keep as-is
        body = {
            "detail": detail,
            "status_code": status_code,
            "error": _error_code(status_code),
        }
    else:
        body = ErrorDetail(
            detail=str(detail),
            status_code=status_code,
            error=_error_code(status_code),
        ).model_dump(exclude_none=True)
    return JSONResponse(status_code=status_code, content=body)


async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """Handle Pydantic/FastAPI validation errors (422) with consistent format."""
    items = [
        ValidationErrorItem(
            loc=list(e["loc"]),
            msg=e.get("msg", "Validation error"),
            type=e.get("type"),
        )
        for e in exc.errors()
    ]
    body = {
        "detail": [i.model_dump() for i in items],
        "status_code": status.HTTP_422_UNPROCESSABLE_ENTITY,
        "error": "validation_error",
    }
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content=body,
    )


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Catch-all for unhandled exceptions; log and return 500."""
    logger.exception("Unhandled exception: %s", exc)
    body = ErrorDetail(
        detail="An unexpected error occurred. Please try again later.",
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        error="internal_server_error",
    ).model_dump(exclude_none=True)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=body,
    )


def register_exception_handlers(app: FastAPI) -> None:
    """Register global exception handlers on the FastAPI app."""
    from fastapi import HTTPException

    app.add_exception_handler(HTTPException, http_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)
