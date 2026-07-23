"""Running *Pipeline Executions*: dispatch, results, and timeouts.

The `api` service does not run pipelines — it asks an *Orchestrator* to, over
RabbitMQ, and tracks the outcome in its domain model. This service object is
that logic: it publishes a start request, settles the execution when a result
comes back, and is the sole authority on timeouts — if the deadline passes with
no result, it declares the execution failed and tells orchestrators to stop.

It runs entirely on the event loop, so its several entry points (an HTTP request
starting one, a consumed result settling one, a timer firing) never run at the
same instant and need no locking among themselves.
"""

import asyncio
import logging

from musibot.core.execution import (
    PIPELINE_EXECUTION_CONTROL_EXCHANGE,
    PIPELINE_EXECUTIONS_EXCHANGE,
    NameAndVersion,
    PipelineExecutionResult,
    PipelineExecutionStart,
    PipelineExecutionTerminate,
    parse_pipeline_execution_message,
    routing_key,
    serialize_message,
)

from musibot.api.domain import (
    MusicorpusPage,
    MusicorpusPageRepository,
    PageNotFound,
    PipelineExecution,
)
from musibot.api.messaging import MessagePublisher

logger = logging.getLogger(__name__)


class ExecutionService:
    """Owns the lifecycle of every *Pipeline Execution* the service tracks."""

    def __init__(
        self,
        repository: MusicorpusPageRepository,
        publisher: MessagePublisher,
        *,
        timeout_seconds: float,
    ):
        self._repository = repository
        self._publisher = publisher
        self._timeout_seconds = timeout_seconds
        # Timeout timers are tracked so they can be cancelled at shutdown; a
        # fired timer removes itself.
        self._timers: set[asyncio.Task[None]] = set()

    async def start(
        self,
        page: MusicorpusPage,
        pipeline_name: str,
        pipeline_version: str,
        parameters: dict[str, object],
    ) -> PipelineExecution:
        """Create a *Pipeline Execution* and dispatch it to orchestrators."""
        execution = page.add_execution(pipeline_name, pipeline_version, parameters)

        start = PipelineExecutionStart(
            page_id=page.page_id,
            execution_id=execution.execution_id,
            pipeline=NameAndVersion(name=pipeline_name, version=pipeline_version),
            parameters=parameters,
            timeout_seconds=self._timeout_seconds,
        )
        await self._publisher.publish(
            PIPELINE_EXECUTIONS_EXCHANGE,
            routing_key(pipeline_name, pipeline_version),
            serialize_message(start),
            # The request expires if it reaches a queue nobody is draining, so a
            # pipeline no orchestrator provides fails by timeout, not by hanging.
            expiration_seconds=self._timeout_seconds,
        )
        self._arm_timeout(page.page_id, execution.execution_id)

        logger.info(
            "Started pipeline execution %s/%d (%s %s)",
            page.page_id,
            execution.execution_id,
            pipeline_name,
            pipeline_version,
        )
        return execution

    async def handle_result(self, body: bytes) -> None:
        """Settle an execution from a result message off RabbitMQ."""
        message = parse_pipeline_execution_message(body)
        if not isinstance(message, PipelineExecutionResult):
            return  # not a result — nothing on this exchange should be anything else
        self._settle(message.page_id, message.execution_id, message.state, message.error)

    async def terminate_running(self, page: MusicorpusPage) -> None:
        """Tell orchestrators to stop every running execution of a page.

        Sent when the page is deleted. Best-effort — the execution may finish on
        its own before the message lands, which is fine.
        """
        for execution in page.executions.values():
            if execution.state == "running":
                await self._publish_terminate(page.page_id, execution.execution_id)

    async def shutdown(self) -> None:
        """Cancel outstanding timeout timers. Called at service shutdown."""
        for timer in list(self._timers):
            timer.cancel()

    # --- internals -----------------------------------------------------------

    def _settle(self, page_id: str, execution_id: int, state: str, error: str | None) -> None:
        try:
            page = self._repository.get(page_id)
        except PageNotFound:
            return  # the page was deleted; the result is moot

        execution = page.executions.get(execution_id)
        if execution is None or execution.state != "running":
            # Unknown, or already settled — a result that races a timeout is
            # ignored, whichever arrives second.
            return

        execution.state = "completed" if state == "completed" else "failed"
        execution.error = error
        logger.info("Pipeline execution %s/%d %s", page_id, execution_id, execution.state)

    def _arm_timeout(self, page_id: str, execution_id: int) -> None:
        timer = asyncio.create_task(self._expire_after_timeout(page_id, execution_id))
        self._timers.add(timer)
        timer.add_done_callback(self._timers.discard)

    async def _expire_after_timeout(self, page_id: str, execution_id: int) -> None:
        try:
            await asyncio.sleep(self._timeout_seconds)
        except asyncio.CancelledError:
            return

        try:
            page = self._repository.get(page_id)
        except PageNotFound:
            return

        execution = page.executions.get(execution_id)
        if execution is None or execution.state != "running":
            return  # it finished in time

        execution.state = "failed"
        execution.error = f"Pipeline execution timed out after {self._timeout_seconds:.0f}s"
        logger.warning("Pipeline execution %s/%d timed out", page_id, execution_id)
        await self._publish_terminate(page_id, execution_id)

    async def _publish_terminate(self, page_id: str, execution_id: int) -> None:
        terminate = PipelineExecutionTerminate(page_id=page_id, execution_id=execution_id)
        await self._publisher.publish(
            PIPELINE_EXECUTION_CONTROL_EXCHANGE, "", serialize_message(terminate)
        )
