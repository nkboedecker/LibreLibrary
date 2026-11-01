"""Create the LibreLibrary web application."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import structlog
from fastapi import APIRouter, FastAPI, Request, Response, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
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

_ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    status.HTTP_401_UNAUTHORIZED: {"model": ErrorOut},
    status.HTTP_403_FORBIDDEN: {"model": ErrorOut},
    status.HTTP_404_NOT_FOUND: {"model": ErrorOut},
    status.HTTP_409_CONFLICT: {"model": ErrorOut},
}


def _error(code: int, detail: str, **headers: str) -> JSONResponse:
    return JSONResponse({"detail": detail}, status_code=code, headers=headers or None)


def _add_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(Unauthenticated)
    async def unauthenticated(_request: Request, _error_: Exception) -> Response:
        return _error(401, "Not authenticated", **{"WWW-Authenticate": "Bearer"})

    @app.exception_handler(Denied)
    async def denied(_request: Request, _error_: Exception) -> Response:
        return _error(403, "Not allowed")

    @app.exception_handler(NotFound)
    async def not_found(_request: Request, _error_: Exception) -> Response:
        return _error(404, "Not found")

    @app.exception_handler(Conflict)
    async def conflict(_request: Request, _error_: Exception) -> Response:
        return _error(409, "Conflict with the current state")

    @app.exception_handler(RateLimited)
    async def rate_limited(_request: Request, _error_: Exception) -> Response:
        return _error(429, "Too many attempts. Try again later.")

    @app.exception_handler(DBAPIError)
    async def database_error(_request: Request, error: Exception) -> Response:
        if isinstance(error, DBAPIError) and is_constraint_violation(error):
            return _error(409, "Conflict with the current state")
        structlog.get_logger().error("database_error", kind=type(error).__name__)
        return _error(500, "Internal server error")

    @app.exception_handler(RequestValidationError)
    async def invalid(_request: Request, error: Exception) -> Response:
        """Describe what is wrong without echoing the input, which may be secret."""
        assert isinstance(error, RequestValidationError)  # noqa: S101
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
    _add_error_handlers(app)
    return app
