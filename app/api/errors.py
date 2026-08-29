import structlog
from fastapi import FastAPI, HTTPException, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.core import ErrorCode
from app.core.exceptions import AppError

logger = structlog.get_logger(__name__)


def _request_id(request: Request) -> str | None:
    return getattr(request.state, "request_id", None)


def _error_response(
    status_code: int,
    code: ErrorCode,
    message: str,
    request: Request,
    details: dict | None = None,
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={
            "code": str(code),
            "message": message,
            "request_id": _request_id(request),
            "details": jsonable_encoder(details) if details else None,
        },
    )


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def handle_app_error(request: Request, exc: AppError):
        # Level follows the status: 4xx is the caller's data, 5xx is our bug.
        if exc.http_status >= 500:
            logger.error("http.app_error", exc_info=exc, **exc.log_fields())
        else:
            logger.warning("http.app_error", **exc.log_fields())
        return _error_response(
            exc.http_status, exc.code, exc.message, request, exc.context
        )

    @app.exception_handler(HTTPException)
    async def handle_http_exception(request: Request, exc: HTTPException):
        logger.warning(
            "http.error", status_code=exc.status_code, detail=exc.detail
        )
        code = (
            ErrorCode.INTERNAL_ERROR
            if exc.status_code >= 500
            else ErrorCode.HTTP_ERROR
        )
        return _error_response(exc.status_code, code, str(exc.detail), request)

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(
        request: Request, exc: RequestValidationError
    ):
        logger.warning("http.request_invalid", errors=exc.errors())
        return _error_response(
            422,
            ErrorCode.REQUEST_VALIDATION_FAILED,
            "Request validation failed",
            request,
            {"errors": exc.errors()},
        )

    @app.exception_handler(Exception)
    async def handle_unexpected(request: Request, exc: Exception):
        # Never leak the exception text: it can carry SQL or credentials.
        logger.exception("http.unhandled_exception")
        return _error_response(
            500,
            ErrorCode.INTERNAL_ERROR,
            "Internal server error",
            request,
        )
