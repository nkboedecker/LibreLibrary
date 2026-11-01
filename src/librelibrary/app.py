"""Create the LibreLibrary web application."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import structlog
from fastapi import APIRouter, FastAPI, Request, Response, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from limits.strategies import FixedWindowRateLimiter
from sqlalchemy import Engine
from sqlalchemy.exc import DBAPIError
from starlette.concurrency import run_in_threadpool

from librelibrary import __version__
from librelibrary.api.v1 import accounts, catalog, groups, libraries, responses, system
from librelibrary.auth.ratelimit import DatabaseStorage
from librelibrary.authz.policy import Denied
from librelibrary.db import is_constraint_violation, make_engine
from librelibrary.errors import Conflict, NotFound, RateLimited, Unauthenticated
from librelibrary.logs import configure_logging
from librelibrary.migrate import run_migrations
from librelibrary.proxy import ForwardedProtoMiddleware
from librelibrary.schemas import ErrorOut
from librelibrary.settings import Settings
from librelibrary.ui import pages, works
from librelibrary.ui.deps import LoginRequired
from librelibrary.ui.templating import UI_DIRECTORY, templates

_ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    status.HTTP_401_UNAUTHORIZED: {"model": ErrorOut},
    status.HTTP_403_FORBIDDEN: {"model": ErrorOut},
    status.HTTP_404_NOT_FOUND: {"model": ErrorOut},
    status.HTTP_409_CONFLICT: {"model": ErrorOut},
}


_PAGE_ERRORS = {
    401: ("Sign in required", "Sign in to continue."),
    403: ("Not allowed", "You can't do that."),
    404: ("Not found", "That page doesn't exist, or you can't see it."),
    409: ("Conflict", "That conflicts with the current state."),
    422: ("Invalid request", "Something in the request wasn't valid."),
    429: ("Too many attempts", "Wait a minute and try again."),
    500: ("Something went wrong", "The server hit an error."),
}
_SECURITY_HEADERS = {
    "Content-Security-Policy": (
        "default-src 'self'; frame-ancestors 'none'; form-action 'self'; "
        "base-uri 'none'"
    ),
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "same-origin",
}


def _error(request: Request, code: int, detail: str, **headers: str) -> Response:
    """Answer the API with JSON, and the web interface with a page."""
    if request.url.path.startswith("/api/"):
        return JSONResponse(
            {"detail": detail}, status_code=code, headers=headers or None
        )
    heading, message = _PAGE_ERRORS[code]
    return templates.TemplateResponse(
        request,
        "error.html",
        {"heading": heading, "message": message},
        status_code=code,
    )


def _add_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(LoginRequired)
    async def login_required(_request: Request, _error_: Exception) -> Response:
        return RedirectResponse("/login", status_code=303)

    @app.exception_handler(Unauthenticated)
    async def unauthenticated(request: Request, _error_: Exception) -> Response:
        return _error(
            request, 401, "Not authenticated", **{"WWW-Authenticate": "Bearer"}
        )

    @app.exception_handler(Denied)
    async def denied(request: Request, _error_: Exception) -> Response:
        return _error(request, 403, "Not allowed")

    @app.exception_handler(NotFound)
    async def not_found(request: Request, _error_: Exception) -> Response:
        return _error(request, 404, "Not found")

    @app.exception_handler(Conflict)
    async def conflict(request: Request, _error_: Exception) -> Response:
        return _error(request, 409, "Conflict with the current state")

    @app.exception_handler(RateLimited)
    async def rate_limited(request: Request, _error_: Exception) -> Response:
        return _error(request, 429, "Too many attempts. Try again later.")

    @app.exception_handler(DBAPIError)
    async def database_error(request: Request, error: Exception) -> Response:
        if isinstance(error, DBAPIError) and is_constraint_violation(error):
            return _error(request, 409, "Conflict with the current state")
        structlog.get_logger().error("database_error", kind=type(error).__name__)
        return _error(request, 500, "Internal server error")

    @app.exception_handler(RequestValidationError)
    async def invalid(request: Request, error: Exception) -> Response:
        """Describe what is wrong without echoing the input, which may be secret."""
        assert isinstance(error, RequestValidationError)  # noqa: S101
        if not request.url.path.startswith("/api/"):
            return _error(request, 422, "Invalid request")
        details = [
            {"type": item["type"], "loc": item["loc"], "msg": item["msg"]}
            for item in error.errors()
        ]
        return JSONResponse({"detail": details}, status_code=422)


def create_app(
    settings: Settings | None = None, *, engine: Engine | None = None
) -> FastAPI:
    """Build the application with its routes."""
    settings = settings or Settings()
    engine = engine or make_engine(settings.database_url)

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        configure_logging()
        if settings.run_migrations_on_startup:
            logger = structlog.get_logger()
            logger.info("migrations_starting", reminder="Back up before upgrading.")
            await run_in_threadpool(run_migrations, engine, settings.migrations_dir)
        yield
        engine.dispose()

    # The generated docs stay unserved: the only public route is the health check.
    app = FastAPI(
        title="LibreLibrary",
        version=__version__,
        lifespan=lifespan,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    app.add_middleware(
        ForwardedProtoMiddleware, trusted_proxies=settings.trusted_proxies
    )
    app.state.settings = settings
    app.state.engine = engine
    app.state.login_limiter = FixedWindowRateLimiter(DatabaseStorage(engine))

    api = APIRouter(prefix="/api/v1")
    api.include_router(system.public_router)
    protected = APIRouter(responses=_ERROR_RESPONSES)
    for module in (accounts, catalog, groups, libraries, responses, system):
        protected.include_router(module.router)
    api.include_router(protected)
    app.include_router(api)
    app.include_router(pages.router)
    app.include_router(works.router)
    app.mount("/static", StaticFiles(directory=UI_DIRECTORY / "static"), name="static")

    @app.middleware("http")
    async def secure_pages(request: Request, call_next: Any) -> Response:
        """Add browser protections to every page; the API is JSON only."""
        response: Response = await call_next(request)
        if not request.url.path.startswith("/api/"):
            for name, value in _SECURITY_HEADERS.items():
                response.headers.setdefault(name, value)
            if not request.url.path.startswith("/static/"):
                response.headers.setdefault("Cache-Control", "no-store")
        return response

    _add_error_handlers(app)
    return app
