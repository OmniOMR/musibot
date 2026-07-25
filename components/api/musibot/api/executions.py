"""Running *Pipeline Executions*: dispatch, results, and timeouts.

For an ordinary *Pipeline* the `api` service does not run anything — it asks an
*Orchestrator* to, over RabbitMQ, and tracks the outcome in its domain model.
For an *ImplicitPipeline* — the one Musibot offers for every known *Model*, so
that a *Model* can be run in isolation — there is nothing to ask, so this
service dispatches the *Model* execution itself and settles the *Pipeline
Execution* from its result. That is what lets Musibot function with no
*Orchestrator* deployed at all; nothing on the wire distinguishes the two cases
to a *Worker Head*.

Either way this object owns the lifecycle: it publishes a start request, settles
the execution when a result comes back, and is the sole authority on timeouts —
if the deadline passes with no result, it declares the execution failed and
tells whoever took the work to stop.

It runs entirely on the event loop, so its several entry points (an HTTP request
starting one, a consumed result settling one, a timer firing) never run at the
same instant and need no locking among themselves.
"""

import asyncio
import logging

from musibot.core.discovery import ModelDescription, generate_instance_id
from musibot.core.execution import (
    MODEL_EXECUTION_CONTROL_EXCHANGE,
    MODEL_EXECUTIONS_EXCHANGE,
    PIPELINE_EXECUTION_CONTROL_EXCHANGE,
    PIPELINE_EXECUTIONS_EXCHANGE,
    ModelExecutionResult,
    ModelExecutionStart,
    ModelExecutionTerminate,
    NameAndVersion,
    PipelineExecutionRef,
    PipelineExecutionResult,
    PipelineExecutionStart,
    PipelineExecutionTerminate,
    generate_model_execution_id,
    parse_model_execution_message,
    parse_pipeline_execution_message,
    routing_key,
    serialize_message,
)

from musibot.api.discovery import ProviderRegistry
from musibot.api.domain import (
    MusicorpusPage,
    MusicorpusPageRepository,
    PageNotFound,
    PipelineExecution,
)
from musibot.api.messaging import MessagePublisher

logger = logging.getLogger(__name__)

REPLY_QUEUE_PREFIX = "musibot.api-replies."
"""Results of *Model* executions this service requested come back to a queue of
its own, named after the instance so that two `api` services never share one."""


class PipelineNotFound(LookupError):
    """Raised when nothing announces the requested *Pipeline* or *Model*.

    Failing here rather than dispatching into the void is deliberate: a typo in
    a pipeline name is far more common than a request racing a fresh deployment,
    and failing immediately beats timing out a minute later.
    """


class ExecutionService:
    """Owns the lifecycle of every *Pipeline Execution* the service tracks."""

    def __init__(
        self,
        repository: MusicorpusPageRepository,
        publisher: MessagePublisher,
        registry: ProviderRegistry,
        *,
        timeout_seconds: float,
        instance_id: str | None = None,
    ):
        self._repository = repository
        self._publisher = publisher
        self._registry = registry
        self._timeout_seconds = timeout_seconds
        self.reply_queue = REPLY_QUEUE_PREFIX + (instance_id or generate_instance_id())
        # Timeout timers are tracked so they can be cancelled at shutdown; a
        # fired timer removes itself.
        self._timers: set[asyncio.Task[None]] = set()
        # The Model executions this service is running as ImplicitPipelines,
        # mapping each back to the Pipeline Execution it stands for. Only
        # in-flight ones are here; settling removes the entry.
        self._model_executions: dict[str, tuple[str, int]] = {}

    async def start(
        self,
        page: MusicorpusPage,
        pipeline_name: str,
        pipeline_version: str,
        parameters: dict[str, object],
    ) -> PipelineExecution:
        """Create a *Pipeline Execution* and dispatch it.

        An explicit *Pipeline* goes to whichever *Orchestrator* provides it; an
        *ImplicitPipeline* is dispatched by this service straight to a *Worker*.
        The explicit one wins if both exist, matching the listing, where the
        colliding *ImplicitPipeline* is the one suppressed.

        Raises :class:`PipelineNotFound` if nothing announces either.
        """
        model = None
        if not self._registry.provides_pipeline(pipeline_name, pipeline_version):
            model = self._registry.find_model(pipeline_name, pipeline_version)
            if model is None:
                raise PipelineNotFound(
                    f"No pipeline or model {pipeline_name!r} version {pipeline_version!r}"
                )

        execution = page.add_execution(pipeline_name, pipeline_version, parameters)

        if model is None:
            await self._dispatch_to_orchestrator(page, execution, parameters)
        else:
            await self._dispatch_to_worker(page, execution, model, parameters)

        self._arm_timeout(page.page_id, execution.execution_id)

        logger.info(
            "Started %spipeline execution %s/%d (%s %s)",
            "implicit " if model is not None else "",
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

    async def handle_model_result(self, body: bytes) -> None:
        """Settle an *ImplicitPipeline* from the result of its one *Model* run.

        Arrives on this service's own reply queue, so it is by construction a
        result for work this service requested.
        """
        message = parse_model_execution_message(body)
        if not isinstance(message, ModelExecutionResult):
            return  # only results come back to a reply queue

        reference = self._model_executions.pop(message.model_execution_id, None)
        if reference is None:
            # Already settled, or belonging to an execution that has since timed
            # out — either way nobody is waiting for this any more.
            return

        page_id, execution_id = reference
        self._settle(page_id, execution_id, message.state, message.error)

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

    # --- dispatch ------------------------------------------------------------

    async def _dispatch_to_orchestrator(
        self,
        page: MusicorpusPage,
        execution: PipelineExecution,
        parameters: dict[str, object],
    ) -> None:
        """Ask whichever *Orchestrator* provides this *Pipeline* to run it."""
        start = PipelineExecutionStart(
            page_id=page.page_id,
            execution_id=execution.execution_id,
            pipeline=NameAndVersion(
                name=execution.pipeline_name, version=execution.pipeline_version
            ),
            parameters=parameters,
            timeout_seconds=self._timeout_seconds,
        )
        await self._publisher.publish(
            PIPELINE_EXECUTIONS_EXCHANGE,
            routing_key(execution.pipeline_name, execution.pipeline_version),
            serialize_message(start),
            # The request expires if it reaches a queue nobody is draining, so a
            # pipeline no orchestrator provides fails by timeout, not by hanging.
            expiration_seconds=self._timeout_seconds,
        )

    async def _dispatch_to_worker(
        self,
        page: MusicorpusPage,
        execution: PipelineExecution,
        model: ModelDescription,
        parameters: dict[str, object],
    ) -> None:
        """Run an *ImplicitPipeline*: one *Model*, requested by this service.

        Nothing in the message says the requester is the `api` service rather
        than an *Orchestrator Head* — which is exactly what lets a *Model* be
        executed with no *Orchestrator* deployed anywhere.
        """
        model_execution_id = generate_model_execution_id()
        self._model_executions[model_execution_id] = (page.page_id, execution.execution_id)

        start = ModelExecutionStart(
            model_execution_id=model_execution_id,
            model=NameAndVersion(name=model.name, version=model.version),
            page_id=page.page_id,
            # The Model is the source of truth for what it reads, so its
            # announced signature is what the Worker Head is told to stage.
            input=list(model.signature.input),
            parameters=parameters,
            pipeline_execution=PipelineExecutionRef(
                page_id=page.page_id, execution_id=execution.execution_id
            ),
            timeout_seconds=self._timeout_seconds,
        )
        await self._publisher.publish(
            MODEL_EXECUTIONS_EXCHANGE,
            routing_key(model.name, model.version),
            serialize_message(start),
            expiration_seconds=self._timeout_seconds,
            reply_to=self.reply_queue,
            correlation_id=model_execution_id,
        )

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
        """Tell whoever took the work to stop.

        For an *ImplicitPipeline* that is a *Worker*, since this service is the
        one orchestrating it; for anything else it is the *Orchestrators*.
        Best-effort either way — a *Model* already working runs to completion
        and its result is simply discarded.
        """
        model_execution_id = self._forget_model_execution(page_id, execution_id)

        if model_execution_id is not None:
            await self._publisher.publish(
                MODEL_EXECUTION_CONTROL_EXCHANGE,
                "",
                serialize_message(ModelExecutionTerminate(model_execution_id=model_execution_id)),
            )
            return

        terminate = PipelineExecutionTerminate(page_id=page_id, execution_id=execution_id)
        await self._publisher.publish(
            PIPELINE_EXECUTION_CONTROL_EXCHANGE, "", serialize_message(terminate)
        )

    def _forget_model_execution(self, page_id: str, execution_id: int) -> str | None:
        """Drop and return the *Model* execution standing in for this *Pipeline
        Execution*, if it is an *ImplicitPipeline*.

        Scanned rather than kept in a reverse index: only executions still in
        flight are held here, and this service runs a handful at a time.
        """
        for model_execution_id, reference in self._model_executions.items():
            if reference == (page_id, execution_id):
                del self._model_executions[model_execution_id]
                return model_execution_id
        return None
