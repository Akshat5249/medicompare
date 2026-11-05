"""FastAPI application: routes, problem-details errors, security headers and origin checks."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from urllib.parse import urlsplit

import structlog
from fastapi import FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api import accounts, admin, prescriptions, public
from app.config import get_settings
from app.core import ProblemError, problem_response

logging.basicConfig(level=get_settings().log_level)
structlog.configure(
    processors=[
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.format_exc_info,
        structlog.processors.JSONRenderer(),
    ]
)
log = structlog.get_logger()
UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}

app = FastAPI(
    title="MediCompare API",
    version="1.0.0",
    summary="Neutral, source-traceable medicine price information for India.",
    description=(
        "Information only, not medical advice. MediCompare does not sell, prescribe or dispense medicines. "
        "State-changing requests require the session's X-CSRF-Token header. Errors use RFC 9457 problem details."
    ),
    openapi_url="/api/v1/openapi.json",
    docs_url="/api/v1/docs",
    redoc_url=None,
)


@app.exception_handler(ProblemError)
def _problem(_: Request, exc: ProblemError) -> Response:
    return problem_response(exc.status, exc.code, exc.title, exc.detail, **exc.extra)


@app.exception_handler(RequestValidationError)
def _validation(_: Request, exc: RequestValidationError) -> Response:
    # Input values are left out on purpose: they may contain health information.
    errors = [
        {"field": ".".join(str(p) for p in e["loc"]), "message": e["msg"]} for e in exc.errors()
    ]
    return problem_response(422, "validation_error", "The request is not valid", errors=errors)


@app.exception_handler(StarletteHTTPException)
def _http(_: Request, exc: StarletteHTTPException) -> Response:
    return problem_response(exc.status_code, f"http_{exc.status_code}", str(exc.detail))


@app.exception_handler(Exception)
def _unhandled(request: Request, exc: Exception) -> Response:
    log.error("unhandled_error", path=request.url.path, error_type=type(exc).__name__)
    return problem_response(500, "internal_error", "Something went wrong")


@app.middleware("http")
async def security_middleware(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    """Reject cross-site state changes and add security headers to every response."""
    origin = request.headers.get("origin")
    if request.method in UNSAFE_METHODS and origin:
        allowed = urlsplit(get_settings().app_base_url).netloc
        if urlsplit(origin).netloc not in {allowed, request.headers.get("host", "")}:
            return problem_response(403, "bad_origin", "Cross-site request rejected")
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    if not request.url.path.startswith("/api/v1/docs"):
        response.headers["Content-Security-Policy"] = "default-src 'none'; frame-ancestors 'none'"
    if get_settings().cookie_secure:
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response


app.include_router(public.router)
app.include_router(accounts.router)
app.include_router(prescriptions.router)
app.include_router(admin.router)
