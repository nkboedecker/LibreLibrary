"""Create the LibreLibrary web application."""

from fastapi import FastAPI
from pydantic import BaseModel

from librelibrary import __version__


class Health(BaseModel):
    """The response of the health endpoint."""

    status: str
    version: str


def create_app() -> FastAPI:
    """Build the application with its routes."""
    app = FastAPI(title="LibreLibrary", version=__version__)

    @app.get("/api/v1/health", operation_id="health_get", tags=["system"])
    def health() -> Health:
        """Report that the server is running.

        This route is public so that container healthchecks can call it. It
        returns no user data.
        """
        return Health(status="ok", version=__version__)

    return app
