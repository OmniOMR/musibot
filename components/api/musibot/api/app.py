"""The FastAPI application: assembling the `api` service."""

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from aio_pika.abc import ExchangeType
from fastapi import FastAPI
from musibot.core.discovery import (
    DISCOVERY_EXCHANGE,
    DISCOVERY_PROBE_EXCHANGE,
    Probe,
    serialize_message,
)
from musibot.core.execution import (
    MODEL_EXECUTION_CONTROL_EXCHANGE,
    MODEL_EXECUTIONS_EXCHANGE,
    PIPELINE_EXECUTION_CONTROL_EXCHANGE,
    PIPELINE_EXECUTION_RESULTS_EXCHANGE,
    PIPELINE_EXECUTIONS_EXCHANGE,
)
from musibot.core.file_changes import FILE_CHANGES_EXCHANGE
from musibot.core.logs import LOGS_EXCHANGE

from musibot.api.config import ApiSettings
from musibot.api.discovery import ProviderRegistry
from musibot.api.domain import MusicorpusPageRepository
from musibot.api.executions import ExecutionService
from musibot.api.file_changes import FileChangeHub
from musibot.api.logs import LogHub
from musibot.api.messaging import Broker, MessagePublisher
from musibot.api.public import PublicAccess
from musibot.api.routes import (
    executions,
    file_changes,
    files,
    logs,
    pages,
    pipelines,
    public_sessions,
)
from musibot.api.storage import StoragePort

logger = logging.getLogger(__name__)


def create_app(
    settings: ApiSettings,
    *,
    pages_repository: MusicorpusPageRepository | None = None,
    registry: ProviderRegistry | None = None,
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
    providers = registry or ProviderRegistry()
    # Built whether or not there is a broker to feed it: the service's own
    # account of an execution goes through it too, and a hub nobody watches
    # discards everything it is given.
    log_hub = LogHub(repository)
    file_change_hub = FileChangeHub()
    execution_service = (
        ExecutionService(
            repository,
            publisher,
            providers,
            timeout_seconds=settings.pipeline_execution_timeout_seconds,
            logs=log_hub,
        )
        if publisher is not None
        else None
    )
    # Built whether or not the tier is switched on: with it off nothing mints
    # and no session resolves, so the wiring needs no branch and the routes can
    # ask it about every caller.
    public_access = PublicAccess(
        settings, repository, executions=execution_service, storage=storage
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        sweeper: asyncio.Task[None] | None = None
        if settings.public_access_enabled:
            logger.info(
                "Public access is on: at most %d concurrent execution(s) and %.1f GiB "
                "across the whole public tier, sessions lasting %.0fs",
                settings.public_max_concurrent_executions,
                settings.public_storage_quota_bytes / 1024**3,
                settings.public_session_ttl_seconds,
            )
            sweeper = asyncio.create_task(public_access.run_sweeps())

        if broker is not None:
            await broker.connect()
            # Declare the exchanges the service publishes to, then subscribe the
            # results consumer (which declares its own exchange).
            await broker.declare_exchange(PIPELINE_EXECUTIONS_EXCHANGE, ExchangeType.DIRECT)
            await broker.declare_exchange(PIPELINE_EXECUTION_CONTROL_EXCHANGE, ExchangeType.FANOUT)
            # Model executions are dispatched by this service too, for every
            # ImplicitPipeline it runs.
            await broker.declare_exchange(MODEL_EXECUTIONS_EXCHANGE, ExchangeType.DIRECT)
            await broker.declare_exchange(MODEL_EXECUTION_CONTROL_EXCHANGE, ExchangeType.FANOUT)
            if execution_service is not None:
                await broker.subscribe(
                    exchange=PIPELINE_EXECUTION_RESULTS_EXCHANGE,
                    exchange_type=ExchangeType.FANOUT,
                    handler=execution_service.handle_result,
                )
                # The reply queue must exist before any Model execution is
                # dispatched naming it, so it is declared here rather than lazily.
                await broker.declare_reply_queue(
                    execution_service.reply_queue, execution_service.handle_model_result
                )

            # Everything the fleet prints arrives here, whether or not anyone is
            # watching a page — a line for a page nobody watches is dropped, and
            # that is the whole of what happens to it.
            await broker.subscribe(
                exchange=LOGS_EXCHANGE,
                exchange_type=ExchangeType.FANOUT,
                handler=log_hub.handle_message,
            )
            # And the same for the *Files* those executions write, which travel
            # separately: a client wanting to know about a new *File* should not
            # have to read the log to find out.
            await broker.subscribe(
                exchange=FILE_CHANGES_EXCHANGE,
                exchange_type=ExchangeType.FANOUT,
                handler=file_change_hub.handle_message,
            )

            # Listen for announcements before asking for them, so that no reply
            # to the probe arrives before there is a queue to hold it.
            await broker.subscribe(
                exchange=DISCOVERY_EXCHANGE,
                exchange_type=ExchangeType.FANOUT,
                handler=providers.handle_message,
            )
            # The registry starts empty and a restart is common in development,
            # so rather than waiting a whole heartbeat interval to become useful,
            # ask everyone to announce themselves now.
            await broker.declare_exchange(DISCOVERY_PROBE_EXCHANGE, ExchangeType.FANOUT)
            await broker.publish(DISCOVERY_PROBE_EXCHANGE, "", serialize_message(Probe()))
        yield
        if sweeper is not None:
            sweeper.cancel()
        if execution_service is not None:
            await execution_service.shutdown()
        if broker is not None:
            await broker.close()

    app = FastAPI(
        title="Musibot API",
        version="0.1.0",
        lifespan=lifespan,
        # Where this service is mounted as the world addresses it, which is
        # not where it serves. Behind nginx the API answers on /musibot/api
        # while the routes below are still declared at the root, and FastAPI
        # builds the URLs in its interactive docs from this. Left unset, /docs
        # renders a page that then asks for /openapi.json at the wrong place
        # and shows nothing. Empty in development, where there is no prefix.
        root_path=settings.root_path,
    )

    app.state.settings = settings
    app.state.api_tokens = settings.load_api_tokens()
    app.state.pages = repository
    app.state.providers = providers
    app.state.storage = storage
    app.state.executions = execution_service
    app.state.public_access = public_access
    app.state.logs = log_hub
    app.state.file_changes = file_change_hub

    app.include_router(public_sessions.router)
    app.include_router(pages.router)
    app.include_router(files.router)
    app.include_router(executions.router)
    app.include_router(logs.router)
    app.include_router(file_changes.router)
    app.include_router(pipelines.router)

    @app.get("/health", tags=["meta"])
    def health() -> dict[str, str]:
        """Liveness check. Requires no authentication."""
        return {"status": "ok"}

    return app
