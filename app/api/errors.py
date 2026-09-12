import structlog
from fastapi import FastAPI, HTTPException, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.core import ErrorCode
from app.core.exceptions import AppError

logger = structlog.get_logger(__name__)

REDACTED = "[redacted]"

# Field names whose *value* is a credential. Pydantic puts the rejected value
# in `input`, so "password must be at least 5 characters" would otherwise log
# and return the plaintext password the caller just tried.
#
# `loc` is not enough to find it. When a *different* field is the one that
# failed - a missing `login`, say - pydantic reports `loc: ("login",)` and puts
# the **whole request body** in `input`, password included. So the values are
# scrubbed by key wherever they sit, not only when `loc` names them.
SENSITIVE_FIELDS = frozenset(
    {
        "password",
        "hashed_password",
        "token",
        "access_token",
        "refresh_token",
        "secret_key",
        "authorization",
    }
)


def _request_id(request: Request) -> str | None:
    return getattr(request.state, "request_id", None)


def _scrub(value):
    """Replace every value stored under a sensitive key, at any depth."""
    if isinstance(value, dict):
        return {
            key: REDACTED if str(key) in SENSITIVE_FIELDS else _scrub(inner)
            for key, inner in value.items()
        }
    if isinstance(value, list):
        return [_scrub(item) for item in value]
    return value


def redact_validation_errors(errors: list[dict]) -> list[dict]:
    """Strip credential values out of pydantic's error list.

    Applied before the errors are logged *and* before they are returned: the
    same structure feeds both.
    """
    safe: list[dict] = []
    for error in errors:
        location = error.get("loc") or ()
        if any(str(part) in SENSITIVE_FIELDS for part in location):
            # The rejected value itself is the credential.
            error = {**error, "input": REDACTED}
        elif "input" in error:
            # Some other field failed, but `input` may still carry the body.
            error = {**error, "input": _scrub(error["input"])}
        safe.append(error)
    return safe


def _error_response(
    status_code: int,
    code: ErrorCode,
    message: str,
    request: Request,
    details: dict | None = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={
            "code": str(code),
            "message": message,
            "request_id": _request_id(request),
            "details": jsonable_encoder(details) if details else None,
        },
        headers=headers,
    )


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def handle_app_error(request: Request, exc: AppError):
        # Level follows the status: 4xx is the caller's data, 5xx is our bug.
        if exc.http_status >= 500:
            logger.error("http.app_error", exc_info=exc, **exc.log_fields())
        else:
            logger.warning("http.app_error", **exc.log_fields())
        headers = (
            {"WWW-Authenticate": "Bearer"} if exc.http_status == 401 else None
        )
        return _error_response(
            exc.http_status,
            exc.code,
            exc.message,
            request,
            exc.context,
            headers,
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
        errors = redact_validation_errors(exc.errors())
        logger.warning("http.request_invalid", errors=errors)
        return _error_response(
            422,
            ErrorCode.REQUEST_VALIDATION_FAILED,
            "Request validation failed",
            request,
            {"errors": errors},
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
