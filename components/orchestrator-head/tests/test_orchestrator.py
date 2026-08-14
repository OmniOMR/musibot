"""The head: announcing itself, taking work, running Models, and reporting.

RabbitMQ and object storage are faked — those are what a test cannot reasonably
run — and everything else is the real thing, including the *Pipeline* code and
the concurrency around it.
"""

import asyncio
from collections.abc import Callable, Coroutine
from dataclasses import dataclass, field
from typing import Any, TypeVar

import pytest
from musibot.core.discovery import (
    DISCOVERY_EXCHANGE,
    Goodbye,
    OrchestratorAnnouncement,
    Probe,
    parse_discovery_message,
)
from musibot.core.discovery import serialize_message as serialize_discovery_message
from musibot.core.execution import (
    MODEL_EXECUTION_CONTROL_EXCHANGE,
    MODEL_EXECUTIONS_EXCHANGE,
    PIPELINE_EXECUTION_RESULTS_EXCHANGE,
    ModelExecutionResult,
    ModelExecutionStart,
    ModelExecutionTerminate,
    NameAndVersion,
    PipelineExecutionResult,
    PipelineExecutionStart,
    PipelineExecutionTerminate,
    WorkerRef,
    parse_model_execution_message,
    parse_pipeline_execution_message,
    serialize_message,
)
from musibot.core.file_changes import FILE_CHANGES_EXCHANGE, FilesChanged, parse_file_change_message
from musibot.core.logs import LOGS_EXCHANGE, LogMessage, parse_log_message

from musibot.orchestrator_head import Orchestrator, Pipeline, PipelineContext, Signature
from musibot.orchestrator_head.messaging import WorkMessage
from musibot.orchestrator_head.orchestrator import OrchestratorHead
from musibot.orchestrator_head.storage import FileNotInPage

T = TypeVar("T")

PAGE_ID = "7Kf2mP9xLwQa"
HELLO_MODEL = NameAndVersion(name="hello-model", version="1.0.0")


def run(scenario: Callable[[], Coroutine[Any, Any, T]]) -> T:
    return asyncio.run(scenario())


# --- the fakes ---------------------------------------------------------------


@dataclass
class Published:
    exchange: str
    routing_key: str
    body: bytes
    expiration_seconds: float | None = None
    reply_to: str | None = None
    correlation_id: str | None = None


@dataclass
class FakeStorage:
    """A page held in a dict."""

    files: dict[str, bytes] = field(default_factory=dict)

    def read(self, page_id: str, file_path: str) -> bytes:
        try:
            return self.files[file_path]
        except KeyError:
            raise FileNotInPage(f"The file {file_path!r} is not in the page {page_id!r}")

    def write(self, page_id: str, file_path: str, data: bytes) -> None:
        self.files[file_path] = data

    def list_files(self, page_id: str) -> list[str]:
        return sorted(self.files)

    def exists(self, page_id: str, file_path: str) -> bool:
        return file_path in self.files


@dataclass
class FakeBroker:
    """The broker, plus the *Workers* on the other side of it.

    A `model-execution-start` published here is answered the way a *Worker*
    would answer it — writing into the page and reporting — so that a test
    exercises the whole round trip without scheduling anything by hand.
    """

    published: list[Published] = field(default_factory=list)
    head: OrchestratorHead | None = None
    storage: FakeStorage | None = None

    model_state: str = "completed"
    model_error: str | None = None
    model_writes: dict[str, bytes] = field(default_factory=dict)
    answer_models: bool = True

    async def publish(
        self,
        exchange: str,
        routing_key: str,
        body: bytes,
        *,
        expiration_seconds: float | None = None,
        reply_to: str | None = None,
        correlation_id: str | None = None,
    ) -> None:
        self.published.append(
            Published(exchange, routing_key, body, expiration_seconds, reply_to, correlation_id)
        )

        if exchange == MODEL_EXECUTIONS_EXCHANGE and self.answer_models:
            await self._answer_as_a_worker(body)

    async def _answer_as_a_worker(self, body: bytes) -> None:
        start = parse_model_execution_message(body)
        assert isinstance(start, ModelExecutionStart)

        if self.storage is not None:
            for file_path, data in self.model_writes.items():
                self.storage.write(start.page_id, file_path, data)

        assert self.head is not None
        await self.head.handle_model_result(
            serialize_message(
                ModelExecutionResult(
                    model_execution_id=start.model_execution_id,
                    state="completed" if self.model_state == "completed" else "failed",
                    error=self.model_error,
                    worker=WorkerRef(name=start.model.name, instance_id="w-1"),
                )
            )
        )

    # --- reading what went out ----------------------------------------------

    def of(self, exchange: str) -> list[Published]:
        return [message for message in self.published if message.exchange == exchange]

    def results(self) -> list[PipelineExecutionResult]:
        parsed = [
            parse_pipeline_execution_message(message.body)
            for message in self.of(PIPELINE_EXECUTION_RESULTS_EXCHANGE)
        ]
        return [message for message in parsed if isinstance(message, PipelineExecutionResult)]

    def model_starts(self) -> list[ModelExecutionStart]:
        parsed = [
            parse_model_execution_message(message.body)
            for message in self.of(MODEL_EXECUTIONS_EXCHANGE)
        ]
        return [message for message in parsed if isinstance(message, ModelExecutionStart)]

    def logs(self) -> list[LogMessage]:
        return [parse_log_message(message.body) for message in self.of(LOGS_EXCHANGE)]

    def file_changes(self) -> list[FilesChanged]:
        return [
            parse_file_change_message(message.body) for message in self.of(FILE_CHANGES_EXCHANGE)
        ]


@dataclass
class FakeWork:
    """A work message, remembering whether it was acknowledged."""

    body: bytes
    acknowledged: int = 0

    async def ack(self) -> None:
        self.acknowledged += 1

    def message(self) -> WorkMessage:
        return WorkMessage(body=self.body, ack=self.ack)


# --- the pipelines under test ------------------------------------------------


class Doubling(Pipeline):
    name, version = "doubling", "1.0.0"
    signature = Signature(input=["image.jpg"], output=["doubled.bin"])

    async def execute(self, ctx: PipelineContext) -> None:
        ctx.logger.info("doubling %s", ctx.input[0])
        await ctx.write_bytes("doubled.bin", await ctx.read_bytes("image.jpg") * 2)


class Failing(Pipeline):
    name, version = "failing", "1.0.0"
    signature = Signature(input=["image.jpg"])

    async def execute(self, ctx: PipelineContext) -> None:
        raise RuntimeError("No staves found in the image.")


class RunsAModel(Pipeline):
    name, version = "runs-a-model", "1.0.0"
    signature = Signature(input=["image.jpg"], output=["transcription.musicxml"])

    async def execute(self, ctx: PipelineContext) -> None:
        await ctx.execute_model(HELLO_MODEL, input=["image.jpg"])
        ctx.logger.info(
            "the model wrote %d bytes", len(await ctx.read_bytes("transcription.musicxml"))
        )


class Waiting(Pipeline):
    """Runs until something cancels it, and says when it has started."""

    name, version = "waiting", "1.0.0"
    signature = Signature()
    started = asyncio.Event()

    async def execute(self, ctx: PipelineContext) -> None:
        self.started.set()
        await asyncio.sleep(3600)


# --- building the head -------------------------------------------------------


def a_head(
    *pipelines: Pipeline,
    broker: FakeBroker,
    storage: FakeStorage | None = None,
    max_concurrent_executions: int = 4,
) -> OrchestratorHead:
    storage = storage if storage is not None else FakeStorage()
    head = OrchestratorHead(
        "test-orchestrator",
        {(pipeline.name, pipeline.version): pipeline for pipeline in pipelines},
        storage,
        broker,
        max_concurrent_executions=max_concurrent_executions,
        instance_id="o-1",
    )
    broker.head = head
    broker.storage = storage
    return head


def a_start(
    pipeline: Pipeline,
    *,
    input: list[str] | None = None,
    execution_id: int = 1,
    timeout_seconds: float = 300,
) -> FakeWork:
    return FakeWork(
        serialize_message(
            PipelineExecutionStart(
                page_id=PAGE_ID,
                execution_id=execution_id,
                pipeline=NameAndVersion(name=pipeline.name, version=pipeline.version),
                input=input if input is not None else ["image.jpg"],
                timeout_seconds=timeout_seconds,
            )
        )
    )


# --- discovery ---------------------------------------------------------------


def test_an_announcement_names_every_registered_pipeline() -> None:
    broker = FakeBroker()
    head = a_head(Doubling(), RunsAModel(), broker=broker)

    announcement = head.announcement()

    assert announcement.provider.name == "test-orchestrator"
    assert announcement.provider.instance_id == "o-1"
    assert [(entry.name, entry.version) for entry in announcement.pipelines] == [
        ("doubling", "1.0.0"),
        ("runs-a-model", "1.0.0"),
    ]
    assert announcement.pipelines[0].signature.output == ["doubled.bin"]


def test_a_probe_is_answered_with_an_announcement() -> None:
    async def scenario() -> None:
        broker = FakeBroker()
        head = a_head(Doubling(), broker=broker)

        await head.handle_probe(serialize_discovery_message(Probe()))

        [message] = broker.of(DISCOVERY_EXCHANGE)
        assert isinstance(parse_discovery_message(message.body), OrchestratorAnnouncement)

    run(scenario)


def test_a_goodbye_names_this_instance() -> None:
    async def scenario() -> None:
        broker = FakeBroker()
        head = a_head(Doubling(), broker=broker)

        await head.say_goodbye()

        [message] = broker.of(DISCOVERY_EXCHANGE)
        goodbye = parse_discovery_message(message.body)
        assert isinstance(goodbye, Goodbye)
        assert goodbye.provider.instance_id == "o-1"

    run(scenario)


# --- running a pipeline ------------------------------------------------------


def test_an_execution_runs_the_pipeline_and_reports_it() -> None:
    async def scenario() -> None:
        broker = FakeBroker()
        storage = FakeStorage({"image.jpg": b"abc"})
        head = a_head(Doubling(), broker=broker, storage=storage)
        work = a_start(Doubling())

        await head.handle_start(work.message())

        assert storage.files["doubled.bin"] == b"abcabc"

        [result] = broker.results()
        assert result.state == "completed"
        assert result.error is None
        assert (result.page_id, result.execution_id) == (PAGE_ID, 1)
        assert result.orchestrator.name == "test-orchestrator"
        assert result.orchestrator.instance_id == "o-1"

    run(scenario)


def test_work_is_acknowledged_once_the_execution_begins() -> None:
    # Never when it ends: an Orchestrator that dies mid-execution must not have
    # its work redelivered and every Model in it run a second time.
    async def scenario() -> None:
        broker = FakeBroker()
        head = a_head(Doubling(), broker=broker, storage=FakeStorage({"image.jpg": b"abc"}))
        work = a_start(Doubling())

        await head.handle_start(work.message())

        assert work.acknowledged == 1

    run(scenario)


def test_what_a_pipeline_says_reaches_the_log_exchange() -> None:
    async def scenario() -> None:
        broker = FakeBroker()
        head = a_head(Doubling(), broker=broker, storage=FakeStorage({"image.jpg": b"abc"}))

        await head.handle_start(a_start(Doubling()).message())
        # The log is published by a task of its own, so that a Pipeline saying
        # something never awaits the broker.
        await head.deliver_pending()

        [line] = broker.logs()
        assert line.message == "doubling image.jpg"
        assert line.source.kind == "orchestrator"
        assert line.source.name == "test-orchestrator"
        assert line.pipeline_execution.page_id == PAGE_ID
        assert line.pipeline_execution.execution_id == 1

    run(scenario)


def test_a_file_a_pipeline_wrote_is_announced() -> None:
    async def scenario() -> None:
        broker = FakeBroker()
        head = a_head(Doubling(), broker=broker, storage=FakeStorage({"image.jpg": b"abc"}))

        await head.handle_start(a_start(Doubling()).message())
        await head.deliver_pending()

        [notice] = broker.file_changes()
        assert notice.paths == ["doubled.bin"]
        assert notice.pipeline_execution.execution_id == 1

    run(scenario)


def test_a_pipeline_that_raises_is_reported_failed_with_its_reason() -> None:
    async def scenario() -> None:
        broker = FakeBroker()
        head = a_head(Failing(), broker=broker)

        await head.handle_start(a_start(Failing()).message())
        await head.deliver_pending()

        [result] = broker.results()
        assert result.state == "failed"
        assert result.error == "No staves found in the image."

        # And said in the log too, because the result goes to the api service
        # while the log goes to the User who was watching.
        assert [(line.level, line.message) for line in broker.logs()] == [
            ("error", "No staves found in the image.")
        ]

    run(scenario)


def test_an_execution_that_outruns_its_timeout_is_reported_failed() -> None:
    async def scenario() -> None:
        broker = FakeBroker()
        head = a_head(Waiting(), broker=broker)

        await head.handle_start(a_start(Waiting(), input=[], timeout_seconds=0.05).message())

        [result] = broker.results()
        assert result.state == "failed"
        assert "did not finish within" in (result.error or "")

    run(scenario)


def test_work_for_a_pipeline_this_orchestrator_does_not_provide_is_dropped() -> None:
    async def scenario() -> None:
        broker = FakeBroker()
        head = a_head(Doubling(), broker=broker)
        work = a_start(Failing())  # registered nowhere

        await head.handle_start(work.message())

        # Acknowledged so it is not redelivered here forever, and not failed —
        # another Orchestrator may be the one that provides it.
        assert work.acknowledged == 1
        assert broker.results() == []

    run(scenario)


def test_a_terminated_execution_is_cancelled_and_not_reported() -> None:
    async def scenario() -> None:
        broker = FakeBroker()
        pipeline = Waiting()
        pipeline.started = asyncio.Event()
        head = a_head(pipeline, broker=broker)

        running = asyncio.create_task(head.handle_start(a_start(pipeline, input=[]).message()))
        await pipeline.started.wait()

        await head.handle_terminate(
            serialize_message(PipelineExecutionTerminate(page_id=PAGE_ID, execution_id=1))
        )
        await running

        # Nothing is published: whoever asked for the termination has already
        # settled the execution.
        assert broker.results() == []

    run(scenario)


# --- running a model ---------------------------------------------------------


def test_a_model_execution_is_addressed_to_the_model_and_answers_here() -> None:
    async def scenario() -> None:
        broker = FakeBroker(model_writes={"transcription.musicxml": b"<score/>"})
        head = a_head(RunsAModel(), broker=broker, storage=FakeStorage({"image.jpg": b"abc"}))

        await head.handle_start(a_start(RunsAModel()).message())
        await head.deliver_pending()

        [request] = broker.of(MODEL_EXECUTIONS_EXCHANGE)
        assert request.routing_key == "hello-model@1.0.0"
        # The reply comes back to this head, not to the api service — nothing
        # else in the message says who asked.
        assert request.reply_to == "musibot.orchestrator-replies.o-1"

        [start] = broker.model_starts()
        assert start.input == ["image.jpg"]
        assert start.page_id == PAGE_ID
        # So that whatever the Model prints is attributed to this execution.
        assert start.pipeline_execution.execution_id == 1
        # And so that nothing this Orchestrator dispatches outlives it.
        assert 0 < start.timeout_seconds <= 300

        assert [line.message for line in broker.logs()] == ["the model wrote 8 bytes"]
        assert broker.results()[0].state == "completed"

    run(scenario)


def test_a_model_that_fails_fails_the_pipeline_with_its_reason() -> None:
    async def scenario() -> None:
        broker = FakeBroker(model_state="failed", model_error="No staves found in the image.")
        head = a_head(RunsAModel(), broker=broker, storage=FakeStorage({"image.jpg": b"abc"}))

        await head.handle_start(a_start(RunsAModel()).message())

        [result] = broker.results()
        assert result.state == "failed"
        assert "hello-model" in (result.error or "")
        assert "No staves found in the image." in (result.error or "")

    run(scenario)


def test_giving_up_on_a_model_tells_the_worker_to_stop() -> None:
    async def scenario() -> None:
        # Nobody answers, so the pipeline's own deadline is what ends it.
        broker = FakeBroker(answer_models=False)
        head = a_head(RunsAModel(), broker=broker, storage=FakeStorage({"image.jpg": b"abc"}))

        await head.handle_start(a_start(RunsAModel(), timeout_seconds=0.05).message())
        await head.deliver_pending()

        [terminate] = [
            parse_model_execution_message(message.body)
            for message in broker.of(MODEL_EXECUTION_CONTROL_EXCHANGE)
        ]
        assert isinstance(terminate, ModelExecutionTerminate)
        assert terminate.model_execution_id == broker.model_starts()[0].model_execution_id

        assert broker.results()[0].state == "failed"

    run(scenario)


def test_a_result_nobody_is_waiting_for_is_ignored() -> None:
    async def scenario() -> None:
        broker = FakeBroker()
        head = a_head(RunsAModel(), broker=broker)

        await head.handle_model_result(
            serialize_message(
                ModelExecutionResult(
                    model_execution_id="8Lw4tR6yBn1c",
                    state="completed",
                    worker=WorkerRef(name="hello-model", instance_id="w-1"),
                )
            )
        )

    run(scenario)


# --- concurrency -------------------------------------------------------------


def test_only_so_many_executions_run_at_once() -> None:
    """The semaphore, not the broker's prefetch, is what bounds them.

    An execution is acknowledged when it begins, so the count of unacknowledged
    messages says nothing about how many are running.
    """

    class Counting(Pipeline):
        name, version = "counting", "1.0.0"
        signature = Signature()
        running = 0
        highest = 0

        async def execute(self, ctx: PipelineContext) -> None:
            type(self).running += 1
            type(self).highest = max(type(self).highest, type(self).running)
            await asyncio.sleep(0.01)
            type(self).running -= 1

    async def scenario() -> None:
        broker = FakeBroker()
        pipeline = Counting()
        head = a_head(pipeline, broker=broker, max_concurrent_executions=2)

        await asyncio.gather(
            *(
                head.handle_start(a_start(pipeline, input=[], execution_id=n).message())
                for n in range(1, 7)
            )
        )

        assert Counting.highest == 2
        assert len(broker.results()) == 6

    run(scenario)


# --- registration ------------------------------------------------------------


def test_an_orchestrator_refuses_two_pipelines_with_one_name_and_version() -> None:
    orchestrator = Orchestrator("test-orchestrator", _settings())
    orchestrator.register_pipeline(Doubling())

    with pytest.raises(ValueError):
        orchestrator.register_pipeline(Doubling())


def test_two_registrations_of_one_implementation_need_only_differ_by_name() -> None:
    orchestrator = Orchestrator("test-orchestrator", _settings())

    orchestrator.register_pipeline(_named(Doubling(), "doubling"))
    orchestrator.register_pipeline(_named(Doubling(), "doubling-dev"))

    assert len(orchestrator._pipelines) == 2


def _settings() -> Any:
    from musibot.orchestrator_head import OrchestratorHeadSettings

    return OrchestratorHeadSettings.for_testing()


def _named(pipeline: Pipeline, name: str) -> Pipeline:
    pipeline.name = name
    return pipeline
