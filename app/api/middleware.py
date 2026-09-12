import time
import uuid
from collections.abc import Awaitable, Callable

import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.core import elapsed_ms

logger = structlog.get_logger(__name__)

REQUEST_ID_HEADER = "X-Request-ID"


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Bind a request id into structlog contextvars for the whole request.

    Note: bindings made here propagate *into* the endpoint (the child task
    copies the current context), but bindings made inside the endpoint do not
    propagate back out - so the final log line below carries only what is
    bound here. Everything is joined by request_id anyway.
    """

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        # Contextvars survive across requests on a reused task - clearing
        # first is what stops the previous request's fields leaking in.
        structlog.contextvars.clear_contextvars()
        request_id = request.headers.get(REQUEST_ID_HEADER) or uuid.uuid4().hex
        structlog.contextvars.bind_contextvars(
            request_id=request_id,
            method=request.method,
            path=request.url.path,
        )
        request.state.request_id = request_id

        started = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            logger.error(
                "http.request.crashed", duration_ms=elapsed_ms(started)
            )
            raise

        logger.info(
            "http.request.finished",
            status_code=response.status_code,
            duration_ms=elapsed_ms(started),
        )
        response.headers[REQUEST_ID_HEADER] = request_id
        return response
