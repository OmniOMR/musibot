"""The worker: announcing itself, taking work, and answering the requester.

The *Model* here is a real subprocess over real pipes — only object storage and
RabbitMQ are faked, since those are what a test cannot reasonably run.
"""

import asyncio
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from musibot.core.discovery import (
    DISCOVERY_EXCHANGE,
    Goodbye,
    Probe,
    WorkerAnnouncement,
    parse_discovery_message,
)
from musibot.core.discovery import serialize_message as serialize_discovery_message
from musibot.core.execution import (
    ModelExecutionResult,
    ModelExecutionStart,
    ModelExecutionTerminate,
    NameAndVersion,
    PipelineExecutionRef,
    parse_model_execution_message,
    serialize_message,
)

from musibot.worker_head.messaging import DEFAULT_EXCHANGE, WorkMessage
from musibot.worker_head.storage import FileStamp, InputFileMissing
from musibot.worker_head.worker import WorkerHead, work_queue_name
from tests.test_model_process import a_model, run

PAGE_ID = "7Kf2mP9xLwQa"
REPLY_QUEUE = "musibot.api-replies.3xQ7nP2vKm9w"


@dataclass
class Published:
    exchange: str
    routing_key: str
    body: bytes
    correlation_id: str | None


class FakePublisher:
    def __init__(self) -> None:
        self.published: list[Published] = []

    async def publish(
        self,
        exchange: str,
        routing_key: str,
        body: bytes,
        *,
        expiration_seconds: float | None = None,
        correlation_id: str | None = None,
    ) -> None:
        self.published.append(Published(exchange, routing_key, body, correlation_id))

    def results(self) -> list[ModelExecutionResult]:
        parsed = [
            parse_model_execution_message(message.body)
            for message in self.published
            if message.exchange == DEFAULT_EXCHANGE
        ]
        return [message for message in parsed if isinstance(message, ModelExecutionResult)]


class FakeStorage:
    """Object storage that keeps the page folder the tests set up by hand."""

    def __init__(self, pages_dir: Path, *, missing_input: bool = False):
        self._pages_dir = pages_dir
        self._missing_input = missing_input
        self.staged: list[tuple[str, list[str]]] = []
        self.uploaded: list[str] = []
        self.discarded: list[str] = []

    def stage_inputs(self, page_id: str, file_paths: list[str]) -> None:
        if self._missing_input:
            raise InputFileMissing(f"The input file {file_paths[0]!r} is not in the page")
        self.staged.append((page_id, file_paths))
        (self._pages_dir / page_id).mkdir(parents=True, exist_ok=True)

    def snapshot(self, page_id: str) -> dict[str, FileStamp]:
        return {}

    def upload_changes(self, page_id: str, before: dict[str, FileStamp]) -> list[str]:
        page_dir = self._pages_dir / page_id
        self.uploaded = [
            str(path.relative_to(page_dir)) for path in page_dir.rglob("*") if path.is_file()
        ]
        return self.uploaded

    def discard(self, page_id: str) -> None:
        self.discarded.append(page_id)


def a_start(
    model_execution_id: str = "8Lw4tR6yBn1c", input_files: list[str] | None = None
) -> bytes:
    return serialize_message(
        ModelExecutionStart(
            model_execution_id=model_execution_id,
            model=NameAndVersion(name="fake-model", version="1.0.0"),
            page_id=PAGE_ID,
            input=input_files if input_files is not None else ["image.jpg"],
            parameters={},
            pipeline_execution=PipelineExecutionRef(page_id=PAGE_ID, execution_id=1),
            timeout_seconds=300,
        )
    )


def work(body: bytes, reply_to: str | None = REPLY_QUEUE) -> WorkMessage:
    return WorkMessage(body=body, reply_to=reply_to, correlation_id="8Lw4tR6yBn1c")


async def a_worker(
    tmp_path: Path, publisher: FakePublisher, storage: Any, mode: str = "ok"
) -> tuple[WorkerHead, Any]:
    model = a_model(tmp_path, mode=mode)
    await model.ensure_running()
    return WorkerHead(model, storage, publisher, head_version="0.1.0", instance_id="w-1"), model


# --- discovery ---------------------------------------------------------------


def test_it_announces_the_model_it_runs(tmp_path: Path) -> None:
    async def scenario() -> None:
        publisher = FakePublisher()
        worker, model = await a_worker(tmp_path, publisher, FakeStorage(tmp_path))
        try:
            await worker.announce()

            [message] = publisher.published
            assert message.exchange == DISCOVERY_EXCHANGE
            announcement = parse_discovery_message(message.body)
            assert isinstance(announcement, WorkerAnnouncement)
            # A Worker provides exactly one Model, so the provider is named
            # after it and the payload is a single model rather than a list.
            assert announcement.provider.name == "fake-model"
            assert announcement.provider.instance_id == "w-1"
            assert announcement.provider.head_version == "0.1.0"
            assert announcement.model.version == "1.0.0"
            assert announcement.model.signature.output == ["out.txt"]
        finally:
            await model.shutdown()

    run(scenario)


def test_a_probe_is_answered_with_an_announcement(tmp_path: Path) -> None:
    async def scenario() -> None:
        publisher = FakePublisher()
        worker, model = await a_worker(tmp_path, publisher, FakeStorage(tmp_path))
        try:
            await worker.handle_probe(serialize_discovery_message(Probe()))

            [message] = publisher.published
            assert isinstance(parse_discovery_message(message.body), WorkerAnnouncement)
        finally:
            await model.shutdown()

    run(scenario)


def test_a_goodbye_names_this_instance(tmp_path: Path) -> None:
    async def scenario() -> None:
        publisher = FakePublisher()
        worker, model = await a_worker(tmp_path, publisher, FakeStorage(tmp_path))
        try:
            await worker.say_goodbye()

            [message] = publisher.published
            goodbye = parse_discovery_message(message.body)
            assert isinstance(goodbye, Goodbye)
            assert goodbye.provider.instance_id == "w-1"
        finally:
            await model.shutdown()

    run(scenario)


def test_the_work_queue_is_named_after_what_it_consumes() -> None:
    assert work_queue_name("staff-detector", "2026-07-22") == (
        "musibot.model.staff-detector@2026-07-22"
    )


# --- work --------------------------------------------------------------------


def test_an_execution_stages_runs_uploads_and_reports(tmp_path: Path) -> None:
    async def scenario() -> None:
        publisher = FakePublisher()
        storage = FakeStorage(tmp_path)
        worker, model = await a_worker(tmp_path, publisher, storage)
        try:
            await worker.handle_start(work(a_start()))

            assert storage.staged == [(PAGE_ID, ["image.jpg"])]
            # What the model wrote goes back to object storage.
            assert storage.uploaded == ["out.txt"]
            # And the mirror is scratch space, cleared once the execution ends.
            assert storage.discarded == [PAGE_ID]

            [result] = publisher.results()
            assert result.state == "completed"
            assert result.error is None
            assert result.worker.instance_id == "w-1"

            # Straight to the queue the requester named, not to an exchange.
            [message] = [m for m in publisher.published if m.exchange == DEFAULT_EXCHANGE]
            assert message.routing_key == REPLY_QUEUE
            assert message.correlation_id == "8Lw4tR6yBn1c"
        finally:
            await model.shutdown()

    run(scenario)


def test_a_model_failure_is_reported_with_its_error(tmp_path: Path) -> None:
    async def scenario() -> None:
        publisher = FakePublisher()
        storage = FakeStorage(tmp_path)
        worker, model = await a_worker(tmp_path, publisher, storage, mode="fail")
        try:
            await worker.handle_start(work(a_start()))

            [result] = publisher.results()
            assert result.state == "failed"
            assert result.error == "No staves found in the image."
            assert storage.discarded == [PAGE_ID]
        finally:
            await model.shutdown()

    run(scenario)


def test_a_model_that_dies_is_reported_as_failed(tmp_path: Path) -> None:
    async def scenario() -> None:
        publisher = FakePublisher()
        worker, model = await a_worker(tmp_path, publisher, FakeStorage(tmp_path), mode="die")
        try:
            await worker.handle_start(work(a_start()))

            [result] = publisher.results()
            assert result.state == "failed"
            assert "exited without reporting" in (result.error or "")
        finally:
            await model.shutdown()

    run(scenario)


def test_a_missing_input_file_fails_before_the_model_is_bothered(tmp_path: Path) -> None:
    async def scenario() -> None:
        publisher = FakePublisher()
        storage = FakeStorage(tmp_path, missing_input=True)
        worker, model = await a_worker(tmp_path, publisher, storage)
        try:
            await worker.handle_start(work(a_start()))

            [result] = publisher.results()
            assert result.state == "failed"
            # A message that says why, which the Model could not have given.
            assert "image.jpg" in (result.error or "")
            assert storage.uploaded == []
        finally:
            await model.shutdown()

    run(scenario)


def test_an_execution_terminated_before_it_began_is_skipped(tmp_path: Path) -> None:
    async def scenario() -> None:
        publisher = FakePublisher()
        storage = FakeStorage(tmp_path)
        worker, model = await a_worker(tmp_path, publisher, storage)
        try:
            await worker.handle_terminate(
                serialize_message(ModelExecutionTerminate(model_execution_id="8Lw4tR6yBn1c"))
            )
            await worker.handle_start(work(a_start()))

            assert storage.staged == []
            assert publisher.published == []
        finally:
            await model.shutdown()

    run(scenario)


def test_a_terminate_for_something_else_does_not_stop_this_work(tmp_path: Path) -> None:
    async def scenario() -> None:
        publisher = FakePublisher()
        worker, model = await a_worker(tmp_path, publisher, FakeStorage(tmp_path))
        try:
            await worker.handle_terminate(
                serialize_message(ModelExecutionTerminate(model_execution_id="somebody-else"))
            )
            await worker.handle_start(work(a_start()))

            assert publisher.results()[0].state == "completed"
        finally:
            await model.shutdown()

    run(scenario)


def test_a_request_naming_no_reply_queue_is_run_but_not_answered(tmp_path: Path) -> None:
    async def scenario() -> None:
        publisher = FakePublisher()
        storage = FakeStorage(tmp_path)
        worker, model = await a_worker(tmp_path, publisher, storage)
        try:
            await worker.handle_start(work(a_start(), reply_to=None))

            # The work is done — there is simply nowhere to say so.
            assert storage.uploaded == ["out.txt"]
            assert publisher.published == []
        finally:
            await model.shutdown()

    run(scenario)


def test_a_message_that_is_not_a_start_is_ignored(tmp_path: Path) -> None:
    async def scenario() -> None:
        publisher = FakePublisher()
        storage = FakeStorage(tmp_path)
        worker, model = await a_worker(tmp_path, publisher, storage)
        try:
            await worker.handle_start(
                work(serialize_message(ModelExecutionTerminate(model_execution_id="x")))
            )

            assert storage.staged == []
            assert publisher.published == []
        finally:
            await model.shutdown()

    run(scenario)


def test_executions_are_run_one_at_a_time(tmp_path: Path) -> None:
    async def scenario() -> None:
        publisher = FakePublisher()
        storage = FakeStorage(tmp_path)
        worker, model = await a_worker(tmp_path, publisher, storage)
        try:
            # A Model does not multitask, so two requests arriving together are
            # serialized rather than interleaved down the one command pipe.
            await asyncio.gather(
                worker.handle_start(work(a_start("first"))),
                worker.handle_start(work(a_start("second"))),
            )

            states = [result.state for result in publisher.results()]
            assert states == ["completed", "completed"]
            ids = {result.model_execution_id for result in publisher.results()}
            assert ids == {"first", "second"}
        finally:
            await model.shutdown()

    run(scenario)


def test_the_result_is_valid_json_on_the_wire(tmp_path: Path) -> None:
    async def scenario() -> None:
        publisher = FakePublisher()
        worker, model = await a_worker(tmp_path, publisher, FakeStorage(tmp_path))
        try:
            await worker.handle_start(work(a_start()))

            [message] = publisher.published
            assert json.loads(message.body)["type"] == "model-execution-result"
        finally:
            await model.shutdown()

    run(scenario)
