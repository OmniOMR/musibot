"""The *Orchestrator Head* itself: what ties a set of *Pipelines* to Musibot.

It announces the *Pipelines* its *Orchestrator* provides, consumes the work
addressed to each of them, runs the *Pipeline* code in this process, dispatches
whatever *Models* that code invokes to *Workers*, and reports the outcome to the
`api` service.

`Orchestrator` is the half a *Pipeline* author sees: construct it, register
*Pipelines*, call `run()`. Everything below that is this module's business.

Whatever a *Pipeline* logs goes out on `musibot.logs` as it is said — straight
to the `api` service rather than with the result at the end, so that a *User*
sees a page being read rather than waiting on it. The *Models* it invokes
publish their own output to the same exchange, so the two interleave there
without either passing through the other.
"""

import asyncio
import logging
import random
import signal
from dataclasses import dataclass
from datetime import UTC, datetime
from importlib.metadata import PackageNotFoundError, version

from aio_pika.abc import ExchangeType
from musibot.core import configure_logging
from musibot.core.discovery import (
    DISCOVERY_EXCHANGE,
    DISCOVERY_PROBE_EXCHANGE,
    HEARTBEAT_INTERVAL_SECONDS,
    PROBE_REPLY_MAX_DELAY_SECONDS,
    Goodbye,
    OrchestratorAnnouncement,
    OrchestratorProvider,
    generate_instance_id,
    parse_discovery_message,
)
from musibot.core.discovery import serialize_message as serialize_discovery_message
from musibot.core.execution import (
    MODEL_EXECUTION_CONTROL_EXCHANGE,
    MODEL_EXECUTIONS_EXCHANGE,
    PIPELINE_EXECUTION_CONTROL_EXCHANGE,
    PIPELINE_EXECUTION_RESULTS_EXCHANGE,
    PIPELINE_EXECUTIONS_EXCHANGE,
    ExecutionState,
    ModelExecutionResult,
    ModelExecutionStart,
    ModelExecutionTerminate,
    NameAndVersion,
    OrchestratorRef,
    PipelineExecutionRef,
    PipelineExecutionResult,
    PipelineExecutionStart,
    PipelineExecutionTerminate,
    generate_model_execution_id,
    parse_model_execution_message,
    parse_pipeline_execution_message,
    pipeline_work_queue,
    routing_key,
    serialize_message,
)
from musibot.core.file_changes import FILE_CHANGES_EXCHANGE, FilesChanged
from musibot.core.file_changes import serialize_message as serialize_file_change_message
from musibot.core.logs import LOGS_EXCHANGE, LogLevel, LogMessage, LogSource
from musibot.core.logs import serialize_message as serialize_log_message

from musibot.orchestrator_head.config import OrchestratorHeadSettings
from musibot.orchestrator_head.messaging import Broker, MessagePublisher, WorkMessage
from musibot.orchestrator_head.pipeline import ModelExecutionFailed, Pipeline, PipelineContext
from musibot.orchestrator_head.storage import PageStorage, PageStoragePort

logger = logging.getLogger(__name__)

REPLY_QUEUE_PREFIX = "musibot.orchestrator-replies."
"""Results of the *Model* executions this process requested come back to a queue
of its own, named after the instance so that two *Orchestrators* never share
one."""

PYTHON_LOG_LEVELS: dict[LogLevel, int] = {
    "debug": logging.DEBUG,
    "info": logging.INFO,
    "warning": logging.WARNING,
    "error": logging.ERROR,
}
"""What a *Pipeline's* log levels are in this process's own log, which is the
copy an operator reads."""

MAX_QUEUED_PUBLICATIONS = 1000
"""How many log lines and notices may be waiting to go out before they start
being dropped. A *Pipeline* logging faster than the broker accepts is a
*Pipeline* to fix, and dropping its narration is better than growing without
bound or blocking the work on it."""


def head_version() -> str | None:
    """This head's own version, reported in its announcements."""
    try:
        return version("musibot-orchestrator-head")
    except PackageNotFoundError:
        return None


@dataclass(frozen=True)
class _Publication:
    """One fire-and-forget message waiting to go out."""

    exchange: str
    routing_key: str
    body: bytes


class PipelineExecutionRuntime:
    """One running *Pipeline Execution*, as the *Pipeline* sees the head.

    This is what `PipelineContext` is given: it knows which execution it belongs
    to, which is what lets a log line be attributed and a *Model* execution
    carry the reference that attributes the *Model's* own output.
    """

    def __init__(self, head: "OrchestratorHead", reference: PipelineExecutionRef, deadline: float):
        self._head = head
        self.reference = reference
        self._deadline = deadline

    def remaining_seconds(self) -> float:
        """How long this execution has left.

        A *Model* this *Pipeline* invokes is given exactly this, so that nothing
        an *Orchestrator* dispatches outlives the execution that asked for it —
        a request that arrives after the *User* has already been told the
        pipeline failed is work nobody wants done.
        """
        return max(0.0, self._deadline - asyncio.get_running_loop().time())

    # --- the ExecutionRuntime protocol ---------------------------------------

    def log(self, message: str, level: LogLevel = "info") -> None:
        self._head.publish_log(self.reference, message, level)

    def files_written(self, file_paths: list[str]) -> None:
        self._head.announce_changes(self.reference, file_paths)

    async def execute_model(
        self, model: NameAndVersion, input: list[str], parameters: dict[str, object]
    ) -> None:
        await self._head.execute_model(self, model, input, parameters)


class OrchestratorHead:
    """One *Orchestrator*: this head plus the *Pipelines* it was given."""

    def __init__(
        self,
        name: str,
        pipelines: dict[tuple[str, str], Pipeline],
        storage: PageStoragePort,
        publisher: MessagePublisher,
        *,
        max_concurrent_executions: int = 4,
        instance_id: str | None = None,
    ):
        self.name = name
        self.instance_id = instance_id or generate_instance_id()
        self.reply_queue = REPLY_QUEUE_PREFIX + self.instance_id

        self._pipelines = pipelines
        self._storage = storage
        self._publisher = publisher

        # A Pipeline Execution is acknowledged when it begins, so the count of
        # unacknowledged messages says nothing about how many are running and
        # the broker's prefetch cannot be what bounds them. This is.
        self._slots = asyncio.Semaphore(max_concurrent_executions)

        # The executions running right now, so that a terminate can find one.
        self._running: dict[tuple[str, int], asyncio.Task[None]] = {}

        # The Model executions this head is waiting on, each waiting to be
        # resolved by a result arriving on the reply queue.
        self._pending_models: dict[str, asyncio.Future[ModelExecutionResult]] = {}

        # Log lines and notices, published in order by one task so that a
        # Pipeline can say something without awaiting the broker.
        self._outgoing: asyncio.Queue[_Publication] = asyncio.Queue(MAX_QUEUED_PUBLICATIONS)

    # --- discovery -----------------------------------------------------------

    def provider(self) -> OrchestratorProvider:
        return OrchestratorProvider(
            name=self.name, instance_id=self.instance_id, head_version=head_version()
        )

    def announcement(self) -> OrchestratorAnnouncement:
        """What this *Orchestrator* tells the `api` service it provides."""
        return OrchestratorAnnouncement(
            provider=self.provider(),
            pipelines=[pipeline.description() for pipeline in self._pipelines.values()],
        )

    async def announce(self) -> None:
        await self._publisher.publish(
            DISCOVERY_EXCHANGE, "", serialize_discovery_message(self.announcement())
        )

    async def say_goodbye(self) -> None:
        """Drop out of the listing at once rather than lingering for the TTL."""
        goodbye = Goodbye(provider=self.provider())
        await self._publisher.publish(DISCOVERY_EXCHANGE, "", serialize_discovery_message(goodbye))

    async def handle_probe(self, body: bytes) -> None:
        """Answer an `api` service that has just started with an empty registry.

        The reply waits a random moment so that everything announcing does not
        answer in the same instant.
        """
        parse_discovery_message(body)  # rejects anything that is not ours
        await asyncio.sleep(random.uniform(0, PROBE_REPLY_MAX_DELAY_SECONDS))
        await self.announce()

    async def heartbeat_forever(self) -> None:
        """Repeat the announcement, so that going silent means going away."""
        while True:
            await asyncio.sleep(HEARTBEAT_INTERVAL_SECONDS)
            try:
                await self.announce()
            except Exception:
                logger.exception("Failed to announce; will try again next heartbeat")

    # --- what a Pipeline says while it works ---------------------------------

    def publish_log(
        self, reference: PipelineExecutionRef, message: str, level: LogLevel = "info"
    ) -> None:
        """Queue one log line for whoever is watching that page.

        Not a coroutine, so that a *Pipeline* narrating itself never awaits the
        broker. Nothing acknowledges a log line and one about a page nobody is
        watching is dropped, so a line lost here costs a *User* some output and
        never the work.

        It is also written to this process's own log, exactly as a *Worker Head*
        writes what its *Model* prints. That copy is the one an operator reading
        the journal has — and the only one that survives an execution nobody was
        watching.
        """
        logger.log(
            PYTHON_LOG_LEVELS[level],
            "[%s/%d] %s",
            reference.page_id,
            reference.execution_id,
            message,
        )

        log = LogMessage(
            pipeline_execution=reference,
            source=LogSource(kind="orchestrator", name=self.name, instance_id=self.instance_id),
            level=level,
            message=message,
            timestamp=datetime.now(UTC).isoformat(),
        )
        self._enqueue(_Publication(LOGS_EXCHANGE, "", serialize_log_message(log)))

    def announce_changes(self, reference: PipelineExecutionRef, file_paths: list[str]) -> None:
        """Queue a notice about *Files* that have just reached object storage."""
        notice = FilesChanged(pipeline_execution=reference, paths=file_paths)
        self._enqueue(
            _Publication(FILE_CHANGES_EXCHANGE, "", serialize_file_change_message(notice))
        )

    def _enqueue(self, publication: _Publication) -> None:
        try:
            self._outgoing.put_nowait(publication)
        except asyncio.QueueFull:
            logger.warning("Dropping a message: %d are already queued", MAX_QUEUED_PUBLICATIONS)

    async def deliver_forever(self) -> None:
        """Publish queued messages, in order, for as long as there are any."""
        while True:
            await self._deliver(await self._outgoing.get())

    async def deliver_pending(self) -> None:
        """Publish everything queued right now and return.

        Called when stopping, so that the last thing a *Pipeline* said still
        reaches the *User* who was watching.
        """
        while not self._outgoing.empty():
            await self._deliver(self._outgoing.get_nowait())

    async def _deliver(self, publication: _Publication) -> None:
        try:
            await self._publisher.publish(
                publication.exchange, publication.routing_key, publication.body
            )
        except Exception:
            logger.warning("Could not publish to %r", publication.exchange, exc_info=True)

    # --- running a Pipeline --------------------------------------------------

    async def handle_start(self, work: WorkMessage) -> None:
        """Run one *Pipeline Execution* and report it to the `api` service."""
        message = parse_pipeline_execution_message(work.body)
        if not isinstance(message, PipelineExecutionStart):
            await work.ack()
            return  # nothing else should arrive on a work queue

        pipeline = self._pipelines.get((message.pipeline.name, message.pipeline.version))
        if pipeline is None:
            # Work is routed by name and version, so this means someone bound
            # this queue to something else — worth saying, and not worth failing
            # an execution another Orchestrator may well be about to run.
            logger.warning(
                "Ignoring work for %s %s, which this orchestrator does not provide",
                message.pipeline.name,
                message.pipeline.version,
            )
            await work.ack()
            return

        # Waited for *before* acknowledging: an execution this head cannot start
        # yet stays in the shared queue, where another instance is free to take
        # it. Acknowledging happens the instant the execution begins, and never
        # when it ends — an Orchestrator that dies mid-execution must not have
        # its work redelivered and every Model in it run a second time.
        async with self._slots:
            await work.ack()
            await self._run(pipeline, message)

    async def _run(self, pipeline: Pipeline, message: PipelineExecutionStart) -> None:
        key = (message.page_id, message.execution_id)
        task = asyncio.create_task(self._execute(pipeline, message))
        self._running[key] = task
        try:
            await task
        except asyncio.CancelledError:
            if task.cancelled():
                # Terminated on request. It has reported nothing, deliberately:
                # whoever asked has already settled the execution.
                logger.info("Pipeline execution %s/%d was terminated", *key)
            else:
                # This head is stopping rather than this one execution, so the
                # execution goes with it instead of being left to run against a
                # broker that is about to close.
                task.cancel()
                raise
        finally:
            self._running.pop(key, None)

    async def _execute(self, pipeline: Pipeline, message: PipelineExecutionStart) -> None:
        """Run the *Pipeline* code, then say how it went."""
        reference = PipelineExecutionRef(page_id=message.page_id, execution_id=message.execution_id)
        runtime = PipelineExecutionRuntime(
            self,
            reference,
            deadline=asyncio.get_running_loop().time() + message.timeout_seconds,
        )
        context = PipelineContext(
            page_id=message.page_id,
            execution_id=message.execution_id,
            input=list(message.input),
            parameters=dict(message.parameters),
            storage=self._storage,
            runtime=runtime,
        )

        logger.info(
            "Running pipeline execution %s/%d (%s %s)",
            message.page_id,
            message.execution_id,
            message.pipeline.name,
            message.pipeline.version,
        )

        state: ExecutionState = "completed"
        error: str | None = None
        try:
            # The `api` service is the authority on this deadline and will fail
            # the execution itself. This is here so that a head with no `api`
            # service listening still cannot leak a Pipeline that runs forever.
            async with asyncio.timeout(message.timeout_seconds):
                await pipeline.execute(context)

        except TimeoutError:
            state = "failed"
            error = f"The pipeline did not finish within {message.timeout_seconds:.0f}s"

        except Exception as failure:
            # Deliberately blind: an execution has to be reported one way or the
            # other, or the `api` service waits out the whole timeout for an
            # answer that is never coming.
            logger.warning(
                "Pipeline execution %s/%d failed: %s",
                message.page_id,
                message.execution_id,
                failure,
                exc_info=not isinstance(failure, ModelExecutionFailed),
            )
            state = "failed"
            error = str(failure) or type(failure).__name__

        if error is not None:
            # Said in the log as well as in the result, because the result goes
            # to the `api` service and the log goes to the *User* watching.
            self.publish_log(reference, error, level="error")

        # Everything the Pipeline said goes out before the result does. Log
        # lines are queued while a result is published outright, so without this
        # a *User* watching sees the execution reported finished and then hears
        # the last thing it had to say.
        await self.deliver_pending()
        await self._report(message, state, error)

    async def _report(
        self, message: PipelineExecutionStart, state: ExecutionState, error: str | None
    ) -> None:
        """Tell the `api` service how the execution went."""
        result = PipelineExecutionResult(
            page_id=message.page_id,
            execution_id=message.execution_id,
            state=state,
            error=error,
            orchestrator=OrchestratorRef(name=self.name, instance_id=self.instance_id),
        )
        try:
            await self._publisher.publish(
                PIPELINE_EXECUTION_RESULTS_EXCHANGE, "", serialize_message(result)
            )
        except Exception:
            # Nothing to be done about it here: the `api` service times the
            # execution out, which is the same outcome by a slower road.
            logger.exception(
                "Could not report pipeline execution %s/%d", message.page_id, message.execution_id
            )

    async def handle_terminate(self, body: bytes) -> None:
        """Stop an execution the `api` service has given up on.

        Fanned out to every *Orchestrator*, so one that does not have this
        execution simply has nothing to cancel. No result is published for it:
        whoever asked for the termination has already settled it.
        """
        message = parse_pipeline_execution_message(body)
        if not isinstance(message, PipelineExecutionTerminate):
            return

        task = self._running.get((message.page_id, message.execution_id))
        if task is not None:
            task.cancel()

    # --- running a Model -----------------------------------------------------

    async def execute_model(
        self,
        execution: PipelineExecutionRuntime,
        model: NameAndVersion,
        input: list[str],
        parameters: dict[str, object],
    ) -> None:
        """Ask a *Worker* to run one *Model*, and wait for its answer.

        The request names this head's reply queue, so the result comes back here
        and not to the `api` service — nothing else in the message says who
        asked, which is what lets the `api` service request the very same work
        for an *ImplicitPipeline*.
        """
        model_execution_id = generate_model_execution_id()
        future: asyncio.Future[ModelExecutionResult] = asyncio.get_running_loop().create_future()
        self._pending_models[model_execution_id] = future

        start = ModelExecutionStart(
            model_execution_id=model_execution_id,
            model=model,
            page_id=execution.reference.page_id,
            input=input,
            parameters=parameters,
            # Rides along so that whatever the Model prints is attributed to the
            # Pipeline Execution that caused it, without the Worker Head asking.
            pipeline_execution=execution.reference,
            timeout_seconds=execution.remaining_seconds(),
        )

        try:
            await self._publisher.publish(
                MODEL_EXECUTIONS_EXCHANGE,
                routing_key(model.name, model.version),
                serialize_message(start),
                # The request expires if it reaches a queue nobody is draining,
                # so a Model no Worker provides fails by timeout rather than
                # being run long after this Pipeline gave up on it.
                expiration_seconds=execution.remaining_seconds(),
                reply_to=self.reply_queue,
                correlation_id=model_execution_id,
            )
            result = await future
        except BaseException:
            # `BaseException` because the case this is here for is
            # `CancelledError`: the execution was terminated or ran out of time
            # while this *Model* was still working. It is told to stop rather
            # than left running for a *Pipeline* that is gone — and the message
            # is queued rather than awaited, since publishing during a
            # cancellation must not depend on the event loop's cooperation.
            self._enqueue(
                _Publication(
                    MODEL_EXECUTION_CONTROL_EXCHANGE,
                    "",
                    serialize_message(
                        ModelExecutionTerminate(model_execution_id=model_execution_id)
                    ),
                )
            )
            raise
        finally:
            self._pending_models.pop(model_execution_id, None)

        if result.state != "completed":
            raise ModelExecutionFailed(model, result.error)

    async def handle_model_result(self, body: bytes) -> None:
        """Hand a *Model's* result to the *Pipeline* waiting for it.

        Arrives on this head's own reply queue, so it is by construction an
        answer to something this head asked for.
        """
        message = parse_model_execution_message(body)
        if not isinstance(message, ModelExecutionResult):
            return  # only results come back to a reply queue

        future = self._pending_models.pop(message.model_execution_id, None)
        if future is None or future.done():
            # Already settled, or belonging to an execution that has since been
            # given up on — either way nobody is waiting for this any more.
            return

        future.set_result(message)


async def run_orchestrator(broker: Broker, head: OrchestratorHead) -> None:
    """Bring an *Orchestrator* up and keep it running until cancelled."""
    await broker.declare_exchange(DISCOVERY_EXCHANGE, ExchangeType.FANOUT)
    # Declared before any work is taken, since the first thing a Pipeline says
    # must have somewhere to go. With no `api` service listening these exchanges
    # have no queue bound to them and everything is dropped, which costs nothing.
    await broker.declare_exchange(LOGS_EXCHANGE, ExchangeType.FANOUT)
    await broker.declare_exchange(FILE_CHANGES_EXCHANGE, ExchangeType.FANOUT)
    await broker.declare_exchange(PIPELINE_EXECUTION_RESULTS_EXCHANGE, ExchangeType.FANOUT)
    await broker.declare_exchange(MODEL_EXECUTIONS_EXCHANGE, ExchangeType.DIRECT)
    await broker.declare_exchange(MODEL_EXECUTION_CONTROL_EXCHANGE, ExchangeType.FANOUT)

    # Before any work is consumed: a Pipeline that runs a Model the instant it
    # starts must have somewhere for the answer to come back to.
    await broker.declare_reply_queue(head.reply_queue, head.handle_model_result)

    descriptions = head.announcement().pipelines

    for description in descriptions:
        await broker.consume_work(
            work_queue=pipeline_work_queue(description.name, description.version),
            exchange=PIPELINE_EXECUTIONS_EXCHANGE,
            routing_key=routing_key(description.name, description.version),
            handler=head.handle_start,
        )

    await broker.subscribe(
        exchange=PIPELINE_EXECUTION_CONTROL_EXCHANGE,
        exchange_type=ExchangeType.FANOUT,
        handler=head.handle_terminate,
    )
    await broker.subscribe(
        exchange=DISCOVERY_PROBE_EXCHANGE,
        exchange_type=ExchangeType.FANOUT,
        handler=head.handle_probe,
    )

    await head.announce()
    logger.info(
        "Orchestrator %s (instance %s) is serving %d pipeline(s): %s",
        head.name,
        head.instance_id,
        len(descriptions),
        ", ".join(f"{d.name} {d.version}" for d in descriptions) or "none",
    )

    delivery = asyncio.create_task(head.deliver_forever())
    heartbeat = asyncio.create_task(head.heartbeat_forever())
    try:
        await heartbeat
    except asyncio.CancelledError:
        # A graceful stop: flush what the running Pipelines said, then say
        # goodbye so the api service drops this Orchestrator from its listing
        # now rather than in thirty seconds.
        heartbeat.cancel()
        delivery.cancel()
        try:
            await head.deliver_pending()
            await head.say_goodbye()
        except Exception:
            logger.warning("Could not say goodbye", exc_info=True)
        raise


class Orchestrator:
    """A set of *Pipelines*, and the process that runs them.

    This is the whole of an *Orchestrator's* startup script::

        def main() -> None:
            settings = MyOrchestratorSettings.load()

            orchestrator = Orchestrator("my-orchestrator", settings)
            orchestrator.register_pipeline(MyPipeline("my-pipeline", "1.0.0",
                                                      model=settings.the_model))
            orchestrator.run()

    Settings are loaded first and the *Pipelines* built from them, which is what
    lets a command line argument reach a *Pipeline's* constructor. See
    `docs/writing-pipelines.md`.
    """

    def __init__(self, name: str, settings: OrchestratorHeadSettings | None = None):
        self.name = name
        """What this *Orchestrator* is called, in the `api` service's listing and
        in the log lines its *Pipelines* produce. Not a setting: an
        *Orchestrator* is a program, and this is which program it is."""

        self.settings = settings or OrchestratorHeadSettings.load()
        self._pipelines: dict[tuple[str, str], Pipeline] = {}

    def register_pipeline(self, pipeline: Pipeline) -> None:
        """Offer one *Pipeline* to Musibot.

        The *Pipeline* is asked to describe itself here rather than when it is
        first announced, so that one that cannot be announced stops the
        *Orchestrator* from starting instead of being found by a *User* who then
        cannot run it.
        """
        description = pipeline.description()
        key = (description.name, description.version)

        if key in self._pipelines:
            raise ValueError(
                f"This orchestrator already provides the pipeline {description.name!r} "
                f"version {description.version!r}. Two registrations of one implementation "
                f"need two names, or two versions."
            )

        self._pipelines[key] = pipeline

    def run(self) -> None:
        """Connect to Musibot and serve the registered *Pipelines* until stopped."""
        configure_logging(self.settings)
        logger.info(
            "Starting the Musibot orchestrator %r with configuration:\n%s",
            self.name,
            self.settings.describe(),
        )
        asyncio.run(self._serve())

    async def _serve(self) -> None:
        broker = Broker(self.settings)
        head = OrchestratorHead(
            self.name,
            self._pipelines,
            PageStorage(self.settings),
            broker,
            max_concurrent_executions=self.settings.max_concurrent_executions,
        )

        await broker.connect(prefetch_count=self.settings.max_concurrent_executions)
        serving = asyncio.create_task(run_orchestrator(broker, head))

        # A stopped Orchestrator says goodbye and flushes what it has to say, so
        # SIGINT and SIGTERM cancel the task rather than tearing the process down.
        loop = asyncio.get_running_loop()
        for received in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(received, serving.cancel)

        try:
            await serving
        except asyncio.CancelledError:
            logger.info("Stopping")
        finally:
            await broker.close()
