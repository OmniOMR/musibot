"""The FastAPI application: assembling the `api` service."""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from aio_pika.abc import ExchangeType
from fastapi import FastAPI
from musibot.core.execution import (
    PIPELINE_EXECUTION_CONTROL_EXCHANGE,
    PIPELINE_EXECUTION_RESULTS_EXCHANGE,
    PIPELINE_EXECUTIONS_EXCHANGE,
)

from musibot.api.config import ApiSettings
from musibot.api.domain import MusicorpusPageRepository
from musibot.api.executions import ExecutionService
from musibot.api.messaging import Broker, MessagePublisher
from musibot.api.routes import executions, files, pages
from musibot.api.storage import StoragePort

logger = logging.getLogger(__name__)


def create_app(
    settings: ApiSettings,
    *,
    pages_repository: MusicorpusPageRepository | None = None,
    storage: StoragePort | None = None,
    publisher: MessagePublisher | None = None,
    broker: Broker | None = None,
) -> FastAPI:
    """Build the application from its settings and collaborators.

    In production, `__main__` passes a real `Broker` as both `publisher` (for
    the routes to publish through) and `broker` (for the lifespan to connect and
    to subscribe the results consumer on). A test passes a fake `publisher` and
    no `broker`, so nothing reaches for RabbitMQ.
    """
    repository = pages_repository or MusicorpusPageRepository()
    execution_service = (
        ExecutionService(
            repository,
            publisher,
            timeout_seconds=settings.pipeline_execution_timeout_seconds,
        )
        if publisher is not None
        else None
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        if broker is not None:
            await broker.connect()
            # Declare the exchanges the service publishes to, then subscribe the
            # results consumer (which declares its own exchange).
            await broker.declare_exchange(PIPELINE_EXECUTIONS_EXCHANGE, ExchangeType.DIRECT)
            await broker.declare_exchange(PIPELINE_EXECUTION_CONTROL_EXCHANGE, ExchangeType.FANOUT)
            if execution_service is not None:
                await broker.subscribe(
                    exchange=PIPELINE_EXECUTION_RESULTS_EXCHANGE,
                    exchange_type=ExchangeType.FANOUT,
                    handler=execution_service.handle_result,
                )
        yield
        if execution_service is not None:
            await execution_service.shutdown()
        if broker is not None:
            await broker.close()

    app = FastAPI(title="Musibot API", version="0.1.0", lifespan=lifespan)

    app.state.settings = settings
    app.state.api_tokens = settings.load_api_tokens()
    app.state.pages = repository
    app.state.storage = storage
    app.state.executions = execution_service

    app.include_router(pages.router)
    app.include_router(files.router)
    app.include_router(executions.router)

    @app.get("/health", tags=["meta"])
    def health() -> dict[str, str]:
        """Liveness check. Requires no authentication."""
        return {"status": "ok"}

    return app
