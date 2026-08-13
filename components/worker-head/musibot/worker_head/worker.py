"""The *Worker Head* itself: what ties a *Model* to the rest of Musibot.

It announces the one *Model* it runs, consumes work addressed to that model's
name and version, stages the *Files* each execution needs, drives the model over
[IPC](../../../../docs/worker-ipc.md), sends back whatever the model produced,
and reports the outcome to whoever asked.

Who asked is not this head's business: a request carries the queue its result
belongs on, and that requester is an *Orchestrator Head* or the `api` service
running an *ImplicitPipeline*, indistinguishably.

Whatever the *Model* prints goes out on `musibot.logs` as it is printed —
straight to the `api` service rather than back through whoever asked, so that a
*User* sees it while an *Orchestrator* is still busy computing.
"""

import asyncio
import logging
import random
from datetime import UTC, datetime

from aio_pika.abc import ExchangeType
from musibot.core.discovery import (
    DISCOVERY_EXCHANGE,
    DISCOVERY_PROBE_EXCHANGE,
    HEARTBEAT_INTERVAL_SECONDS,
    PROBE_REPLY_MAX_DELAY_SECONDS,
    Goodbye,
    WorkerAnnouncement,
    WorkerProvider,
    generate_instance_id,
    parse_discovery_message,
)
from musibot.core.discovery import serialize_message as serialize_discovery_message
from musibot.core.execution import (
    MODEL_EXECUTION_CONTROL_EXCHANGE,
    MODEL_EXECUTIONS_EXCHANGE,
    ExecutionState,
    ModelExecutionResult,
    ModelExecutionStart,
    ModelExecutionTerminate,
    PipelineExecutionRef,
    WorkerRef,
    parse_model_execution_message,
    routing_key,
    serialize_message,
)
from musibot.core.logs import LOGS_EXCHANGE, LogLevel, LogMessage, LogSource
from musibot.core.logs import serialize_message as serialize_log_message
from musibot.core.patterns import parse_file_patterns

from musibot.worker_head.messaging import (
    DEFAULT_EXCHANGE,
    Broker,
    MessagePublisher,
    WorkMessage,
)
from musibot.worker_head.model_process import ModelFailed, ModelProcess, ModelProtocolError
from musibot.worker_head.storage import FileStamp, InputFileMissing, PageStoragePort

logger = logging.getLogger(__name__)

WORK_QUEUE_PREFIX = "musibot.model."
"""Queues are named after what they consume, so that what a queue is for is
evident in the RabbitMQ management UI."""


def work_queue_name(name: str, version: str) -> str:
    return WORK_QUEUE_PREFIX + routing_key(name, version)


class WorkerHead:
    """One *Worker*: this head plus the single *Model* it drives."""

    def __init__(
        self,
        model: ModelProcess,
        storage: PageStoragePort,
        publisher: MessagePublisher,
        *,
        head_version: str | None = None,
        instance_id: str | None = None,
    ):
        self._model = model
        self._storage = storage
        self._publisher = publisher
        self._head_version = head_version
        self.instance_id = instance_id or generate_instance_id()

        # Taken once, when the Model has said what it is, and kept. A Model that
        # dies mid-execution leaves nothing to ask, yet that is exactly when the
        # failure has to be reported — and reporting it means naming the Worker
        # it came from.
        if model.description is None:
            raise RuntimeError("A Worker is built only once its Model has said `ready`")
        self.description = model.description

        # From here on, everything the Model prints is forwarded to the log
        # exchange as well as to this head's own log. Wired now rather than at
        # construction of the ModelProcess, which happens before there is a
        # Worker to name as the source.
        model.output_sink = self.forward_model_output

        # Executions cancelled before they started. Termination is best-effort
        # and only cancels what has not begun: a Model executes one command at a
        # time and the IPC has no way to interrupt one, so a Model already
        # working runs to completion and its result is simply discarded.
        self._terminated: set[str] = set()

    # --- discovery -----------------------------------------------------------

    def announcement(self) -> WorkerAnnouncement:
        """What this *Worker* tells the `api` service it provides.

        The *Model's* own account of itself, republished — it is the thing that
        knows its name, version and signature.
        """
        description = self.description
        return WorkerAnnouncement(
            provider=WorkerProvider(
                name=description.name,
                instance_id=self.instance_id,
                head_version=self._head_version,
            ),
            model=description,
        )

    async def announce(self) -> None:
        await self._publisher.publish(
            DISCOVERY_EXCHANGE, "", serialize_discovery_message(self.announcement())
        )

    async def say_goodbye(self) -> None:
        """Drop out of the listing at once rather than lingering for the TTL."""
        goodbye = Goodbye(
            provider=WorkerProvider(
                name=self.description.name,
                instance_id=self.instance_id,
                head_version=self._head_version,
            )
        )
        await self._publisher.publish(DISCOVERY_EXCHANGE, "", serialize_discovery_message(goodbye))

    async def handle_probe(self, body: bytes) -> None:
        """Answer an `api` service that has just started with an empty registry.

        The reply waits a random moment so that a hundred *Workers* do not all
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

    # --- the log stream ------------------------------------------------------

    async def forward_model_output(
        self, pipeline_execution: PipelineExecutionRef, line: str, level: LogLevel
    ) -> None:
        """Send one line the *Model* printed on to whoever is watching the page.

        This is the whole reason the IPC keeps the *Model's* stdout and stderr
        free: a model needs no logging setup, and `print("staff 3/12")` reaches
        the *User* by itself.
        """
        await self._publish_log(pipeline_execution, line, level)

    async def _publish_log(
        self, pipeline_execution: PipelineExecutionRef, message: str, level: LogLevel = "info"
    ) -> None:
        """Publish one log line, fire-and-forget.

        Nothing acknowledges it, and if nobody is watching that page the `api`
        service drops it. A failure to publish is therefore not allowed to
        become a failure of the execution: the *User* loses a line of output,
        which is worth far less than the work.
        """
        log = LogMessage(
            pipeline_execution=pipeline_execution,
            source=LogSource(
                kind="worker", name=self.description.name, instance_id=self.instance_id
            ),
            level=level,
            message=message,
            timestamp=datetime.now(UTC).isoformat(),
        )
        try:
            await self._publisher.publish(LOGS_EXCHANGE, "", serialize_log_message(log))
        except Exception:
            logger.warning("Could not publish a log line", exc_info=True)

    # --- work ----------------------------------------------------------------

    async def handle_terminate(self, body: bytes) -> None:
        """Note an execution as cancelled, if it has not started yet."""
        message = parse_model_execution_message(body)
        if not isinstance(message, ModelExecutionTerminate):
            return
        self._terminated.add(message.model_execution_id)

    async def handle_start(self, work: WorkMessage) -> None:
        """Run one model execution and report it to whoever asked."""
        message = parse_model_execution_message(work.body)
        if not isinstance(message, ModelExecutionStart):
            return

        if message.model_execution_id in self._terminated:
            self._terminated.discard(message.model_execution_id)
            logger.info(
                "Skipping model execution %s, which was terminated before it began",
                message.model_execution_id,
            )
            return

        state, error = await self._run(message)
        if state == "failed" and error is not None:
            # Said in the log as well as in the result, because the result goes
            # to whoever asked and the log goes to the *User*: an *Orchestrator*
            # is free to report a failure of its own and lose the model's reason
            # on the way, which is exactly when somebody wants to read it.
            await self._publish_log(message.pipeline_execution, error, level="error")
        await self._report(message, work.reply_to, state, error)

    async def _run(self, message: ModelExecutionStart) -> tuple[ExecutionState, str | None]:
        """Stage, execute, and send back what changed."""
        page_id = message.page_id
        logger.info("Running model execution %s on page %s", message.model_execution_id, page_id)

        try:
            # Every storage call is blocking boto3, so it is kept off the loop.
            await asyncio.to_thread(self._storage.stage_inputs, page_id, list(message.input))
            before = await asyncio.to_thread(self._storage.snapshot, page_id)

            await self._model.execute(
                message.model_execution_id,
                page_id,
                list(message.input),
                dict(message.parameters),
                message.pipeline_execution,
            )

            after = await asyncio.to_thread(self._storage.snapshot, page_id)
            uploaded = await asyncio.to_thread(self._storage.upload_changes, page_id, before)
            logger.info(
                "Model execution %s produced %d file(s): %s",
                message.model_execution_id,
                len(uploaded),
                ", ".join(uploaded) or "none",
            )
            if uploaded:
                # What a Model wrote is the one thing about an execution that a
                # User cannot see until it has finished and they have listed the
                # page, so it is worth a line even from a silent model.
                await self._publish_log(message.pipeline_execution, f"wrote {', '.join(uploaded)}")
            self._warn_about_undeclared(message, uploaded)

            missing = self._missing_promised_outputs(after)
            if missing:
                # Writing output to the wrong path is the commonest way to get a
                # Model wrong, and it otherwise shows up as a Pipeline that
                # succeeds and produces nothing.
                return "failed", (
                    f"The model declares {', '.join(repr(path) for path in missing)} as output "
                    f"but did not write it"
                )

            return "completed", None

        except (ModelFailed, InputFileMissing, ModelProtocolError) as failure:
            logger.warning("Model execution %s failed: %s", message.model_execution_id, failure)
            return "failed", str(failure)

        except Exception as failure:
            # Deliberately blind: an execution has to be reported one way or
            # the other, or whoever asked waits out the whole pipeline timeout
            # for an answer that is never coming.
            logger.exception("Model execution %s failed unexpectedly", message.model_execution_id)
            return "failed", str(failure)

        finally:
            await asyncio.to_thread(self._storage.discard, page_id)

    def _missing_promised_outputs(self, present: dict[str, FileStamp]) -> list[str]:
        """Which *Files* the *Signature* promised outright but are not there.

        Only the slot-free, non-optional entries: how many *Files* fill a
        `Staves/{*}/image.jpg` is the *Model's* to decide, and nothing here
        could say it got the number wrong.
        """
        return [
            file_path
            for file_path in self.description.signature.promised_output_files()
            if file_path not in present
        ]

    def _warn_about_undeclared(self, message: ModelExecutionStart, uploaded: list[str]) -> None:
        """Note *Files* the *Model* wrote that its *Signature* does not describe.

        They are kept — filtering them away would silently swallow a diagnostic
        file somebody meant to keep — but a *Model* producing them is either
        under-declaring itself or writing to the wrong path.
        """
        patterns = parse_file_patterns(self.description.signature.output)
        undeclared = [
            file_path
            for file_path in uploaded
            if not any(pattern.match(file_path) for pattern in patterns)
        ]
        if undeclared:
            logger.warning(
                "Model execution %s wrote %s, which its signature does not declare as output",
                message.model_execution_id,
                ", ".join(repr(file_path) for file_path in undeclared),
            )

    async def _report(
        self,
        message: ModelExecutionStart,
        reply_to: str | None,
        state: ExecutionState,
        error: str | None,
    ) -> None:
        """Send the result back to the queue the requester named.

        Straight to that one queue rather than to a shared exchange: this result
        belongs to the one requester that asked for the work.
        """
        if reply_to is None:
            logger.warning(
                "Model execution %s named no reply queue; its result is dropped",
                message.model_execution_id,
            )
            return

        result = ModelExecutionResult(
            model_execution_id=message.model_execution_id,
            state=state,
            error=error,
            worker=WorkerRef(name=self.description.name, instance_id=self.instance_id),
        )
        await self._publisher.publish(
            DEFAULT_EXCHANGE,
            reply_to,
            serialize_message(result),
            correlation_id=message.model_execution_id,
        )


async def run_worker(
    broker: Broker,
    model: ModelProcess,
    storage: PageStoragePort,
    *,
    head_version: str | None = None,
) -> None:
    """Bring a *Worker* up and keep it running until cancelled.

    The *Model* is started first and nothing is announced or consumed until it
    says `ready` — a model still loading its weights must not be offered work.
    """
    description = await model.ensure_running()
    worker = WorkerHead(model, storage, broker, head_version=head_version)

    await broker.declare_exchange(DISCOVERY_EXCHANGE, ExchangeType.FANOUT)
    # Declared before any work is taken, since the first thing a Model prints
    # must have somewhere to go. With no `api` service listening the exchange
    # has no queue bound to it and every line is dropped, which costs nothing.
    await broker.declare_exchange(LOGS_EXCHANGE, ExchangeType.FANOUT)

    await broker.consume_work(
        queue_name=work_queue_name(description.name, description.version),
        exchange=MODEL_EXECUTIONS_EXCHANGE,
        routing_key=routing_key(description.name, description.version),
        handler=worker.handle_start,
    )
    await broker.subscribe(
        exchange=MODEL_EXECUTION_CONTROL_EXCHANGE,
        exchange_type=ExchangeType.FANOUT,
        handler=worker.handle_terminate,
    )
    await broker.subscribe(
        exchange=DISCOVERY_PROBE_EXCHANGE,
        exchange_type=ExchangeType.FANOUT,
        handler=worker.handle_probe,
    )

    await worker.announce()
    logger.info(
        "Worker %s is serving model %r version %r",
        worker.instance_id,
        description.name,
        description.version,
    )

    heartbeat = asyncio.create_task(worker.heartbeat_forever())
    try:
        await heartbeat
    except asyncio.CancelledError:
        # A graceful stop: say goodbye so the api service drops this Worker from
        # its listing now rather than in thirty seconds.
        heartbeat.cancel()
        try:
            await worker.say_goodbye()
        except Exception:
            logger.warning("Could not say goodbye", exc_info=True)
        raise
