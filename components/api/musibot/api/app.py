"""The FastAPI application: assembling the `api` service."""

import logging

from fastapi import FastAPI

from musibot.api.config import ApiSettings
from musibot.api.domain import MusicorpusPageRepository
from musibot.api.routes import files, pages
from musibot.api.storage import StoragePort

logger = logging.getLogger(__name__)


def create_app(
    settings: ApiSettings,
    pages_repository: MusicorpusPageRepository | None = None,
    storage: StoragePort | None = None,
) -> FastAPI:
    """Build the application from its settings.

    The repository and storage may be passed in for a test; otherwise a fresh
    in-memory repository is created and storage is left unconfigured. Other
    external collaborators (RabbitMQ) are attached here too as they arrive.
    """
    app = FastAPI(title="Musibot API", version="0.1.0")

    app.state.settings = settings
    app.state.api_tokens = settings.load_api_tokens()
    app.state.pages = pages_repository or MusicorpusPageRepository()
    app.state.storage = storage

    app.include_router(pages.router)
    app.include_router(files.router)

    @app.get("/health", tags=["meta"])
    def health() -> dict[str, str]:
        """Liveness check. Requires no authentication."""
        return {"status": "ok"}

    return app
