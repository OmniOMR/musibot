"""The worker: announcing itself, taking work, and answering the requester.

The *Model* here is a real subprocess over real pipes — only object storage and
RabbitMQ are faked, since those are what a test cannot reasonably run.
"""

import asyncio
import json
import shutil
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
from musibot.core.file_changes import FILE_CHANGES_EXCHANGE, FilesChanged, parse_file_change_message
from musibot.core.logs import LOGS_EXCHANGE, LogMessage, parse_log_message

from musibot.worker_head.messaging import DEFAULT_EXCHANGE, WorkMessage
from musibot.worker_head.storage import FileStamp, InputFileMissing
from musibot.worker_head.worker import WorkerHead
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

    def logs(self) -> list[LogMessage]:
        return [
            parse_log_message(message.body)
            for message in self.published
            if message.exchange == LOGS_EXCHANGE
        ]

    def file_changes(self) -> list[FilesChanged]:
        return [
            parse_file_change_message(message.body)
            for message in self.published
            if message.exchange == FILE_CHANGES_EXCHANGE
        ]


class FakeStorage:
    """Object storage that keeps the page folder the tests set up by hand."""

    def __init__(self, pages_dir: Path, *, missing_input: bool = False):
        self._pages_dir = pages_dir
        self._missing_input = missing_input
        self.staged: list[tuple[str, list[str]]] = []
        self.uploaded: list[str] = []
        self.discarded: list[str] = []
        # Staging and discarding in the order they happened, which is what says
        # whether two executions shared one page's mirror.
        self.events: list[tuple[str, str]] = []

    def stage_inputs(self, page_id: str, file_paths: list[str]) -> None:
        if self._missing_input:
            raise InputFileMissing(f"The input file {file_paths[0]!r} is not in the page")
        self.staged.append((page_id, file_paths))
        self.events.append(("staged", page_id))
        (self._pages_dir / page_id).mkdir(parents=True, exist_ok=True)

    def snapshot(self, page_id: str) -> dict[str, FileStamp]:
        page_dir = self._pages_dir / page_id
        if not page_dir.is_dir():
            return {}
        return {
            str(path.relative_to(page_dir)): (path.stat().st_size, path.stat().st_mtime_ns)
            for path in page_dir.rglob("*")
            if path.is_file()
        }

    def upload_changes(self, page_id: str, before: dict[str, FileStamp]) -> list[str]:
        page_dir = self._pages_dir / page_id
        self.uploaded = [
            str(path.relative_to(page_dir)) for path in page_dir.rglob("*") if path.is_file()
        ]
        return self.uploaded

    def discard(self, page_id: str) -> None:
        self.discarded.append(page_id)
        self.events.append(("discarded", page_id))
        shutil.rmtree(self._pages_dir / page_id, ignore_errors=True)


def a_start(
    model_execution_id: str = "8Lw4tR6yBn1c",
    input_files: list[str] | None = None,
    page_id: str = PAGE_ID,
) -> bytes:
    return serialize_message(
        ModelExecutionStart(
            model_execution_id=model_execution_id,
            model=NameAndVersion(name="fake-model", version="1.0.0"),
            page_id=page_id,
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


def test_two_executions_on_one_page_do_not_share_its_mirror(tmp_path: Path) -> None:
    """A *Pipeline* runs one *Model* over every staff of a page at once.

    All of those executions are the same page, and this *Worker* mirrors a page
    into one directory — so if two of them are in flight here at the same time,
    the first to finish deletes the mirror out from under the second, which then
    fails saying that a *File* staged for it does not exist while it sits in
    object storage perfectly intact.

    The events therefore have to nest, `staged … discarded` twice over, and
    never interleave. This is asserted rather than the failure reproduced,
    because the failure needs the two to overlap at just the wrong moment and
    this holds whatever the timing.
    """

    async def scenario() -> None:
        publisher = FakePublisher()
        storage = FakeStorage(tmp_path)
        worker, model = await a_worker(tmp_path, publisher, storage)
        try:
            await asyncio.gather(
                worker.handle_start(work(a_start("execution-one"))),
                worker.handle_start(work(a_start("execution-two"))),
            )

            assert storage.events == [
                ("staged", PAGE_ID),
                ("discarded", PAGE_ID),
                ("staged", PAGE_ID),
                ("discarded", PAGE_ID),
            ]
            assert [result.state for result in publisher.results()] == ["completed", "completed"]
        finally:
            await model.shutdown()

    run(scenario)


def test_executions_on_different_pages_are_not_held_up_by_each_other(tmp_path: Path) -> None:
    # Only the page's own mirror is exclusive. Two pages have two directories
    # and nothing to disagree about, so they overlap as before.
    async def scenario() -> None:
        publisher = FakePublisher()
        storage = FakeStorage(tmp_path)
        worker, model = await a_worker(tmp_path, publisher, storage)
        try:
            other_page = "pageBBBBBBBB"
            await asyncio.gather(
                worker.handle_start(work(a_start("execution-one"))),
                worker.handle_start(work(a_start("execution-two", page_id=other_page))),
            )

            assert storage.events[:2] == [("staged", PAGE_ID), ("staged", other_page)]
            assert [result.state for result in publisher.results()] == ["completed", "completed"]
        finally:
            await model.shutdown()

    run(scenario)


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


def test_a_model_that_did_not_write_its_promised_output_fails(tmp_path: Path) -> None:
    """A *Model* reporting success while writing nowhere its *Signature* names.

    Otherwise this is a *Pipeline* that succeeds and produces nothing, which is
    a miserable thing to debug.
    """

    async def scenario() -> None:
        publisher = FakePublisher()
        storage = FakeStorage(tmp_path)
        worker, model = await a_worker(tmp_path, publisher, storage, mode="wrong-path")
        try:
            await worker.handle_start(work(a_start()))

            [result] = publisher.results()
            assert result.state == "failed"
            assert "'out.txt'" in (result.error or "")

            # The misplaced file still went back: refusing to upload it would
            # hide the evidence of what the model actually did.
            assert storage.uploaded == ["typo.txt"]
        finally:
            await model.shutdown()

    run(scenario)


def test_files_the_signature_does_not_declare_are_still_uploaded(tmp_path: Path) -> None:
    async def scenario() -> None:
        publisher = FakePublisher()
        storage = FakeStorage(tmp_path)
        worker, model = await a_worker(tmp_path, publisher, storage, mode="extra-files")
        try:
            await worker.handle_start(work(a_start()))

            [result] = publisher.results()
            assert result.state == "completed"
            # `warnings.json` is undeclared, and kept anyway — filtering it away
            # would swallow a diagnostic file somebody meant to keep.
            assert sorted(storage.uploaded) == ["out.txt", "warnings.json"]
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
            assert publisher.results() == []
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


# --- file changes ------------------------------------------------------------


def test_the_files_written_are_announced(tmp_path: Path) -> None:
    async def scenario() -> None:
        publisher = FakePublisher()
        worker, model = await a_worker(tmp_path, publisher, FakeStorage(tmp_path))
        try:
            await worker.handle_start(work(a_start()))

            [notice] = publisher.file_changes()
            assert notice.paths == ["out.txt"]
            # Attributed to the execution that wrote them, which is knowable now
            # and never afterwards — a later execution may overwrite this file.
            assert notice.pipeline_execution == PipelineExecutionRef(
                page_id=PAGE_ID, execution_id=1
            )
        finally:
            await model.shutdown()

    run(scenario)


def test_a_notice_comes_after_the_upload(tmp_path: Path) -> None:
    """A client told about a *File* that is not in storage yet would fetch a
    404, which is a race it could not win."""

    uploaded_at: list[int] = []

    class SlowStorage(FakeStorage):
        def upload_changes(self, page_id: str, before: dict[str, FileStamp]) -> list[str]:
            result = super().upload_changes(page_id, before)
            uploaded_at.append(len(publisher.published))
            return result

    publisher = FakePublisher()

    async def scenario() -> None:
        worker, model = await a_worker(tmp_path, publisher, SlowStorage(tmp_path))
        try:
            await worker.handle_start(work(a_start()))

            [when_uploaded] = uploaded_at
            announced_at = [
                index
                for index, message in enumerate(publisher.published)
                if message.exchange == FILE_CHANGES_EXCHANGE
            ]
            assert announced_at == [when_uploaded + 1]
        finally:
            await model.shutdown()

    run(scenario)


def test_an_execution_that_wrote_nothing_announces_nothing(tmp_path: Path) -> None:
    async def scenario() -> None:
        publisher = FakePublisher()
        worker, model = await a_worker(tmp_path, publisher, FakeStorage(tmp_path), mode="fail")
        try:
            await worker.handle_start(work(a_start()))

            assert publisher.file_changes() == []
        finally:
            await model.shutdown()

    run(scenario)


def test_a_broker_that_refuses_a_notice_does_not_fail_the_execution(tmp_path: Path) -> None:
    class RefusingPublisher(FakePublisher):
        async def publish(self, exchange: str, *args: Any, **kwargs: Any) -> None:
            if exchange == FILE_CHANGES_EXCHANGE:
                raise ConnectionError("the broker went away")
            await super().publish(exchange, *args, **kwargs)

    async def scenario() -> None:
        publisher = RefusingPublisher()
        worker, model = await a_worker(tmp_path, publisher, FakeStorage(tmp_path))
        try:
            await worker.handle_start(work(a_start()))

            # Object storage is the truth about what a page holds; a missed
            # notice costs a *User* some latency and never the work.
            [result] = publisher.results()
            assert result.state == "completed"
        finally:
            await model.shutdown()

    run(scenario)


# --- the log stream ----------------------------------------------------------


async def until(condition: Any, what: str, timeout: float = 5.0) -> None:
    """Wait for the *Model's* output to have been drained.

    Output and reports travel on two different pipes read by two different
    tasks, so an execution returning does not mean everything the model printed
    has been read yet — in a running *Worker* those last lines simply arrive a
    moment later, and a test has to wait for them rather than assume.
    """
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while not condition():
        if loop.time() > deadline:
            raise AssertionError(f"Timed out waiting for {what}")
        await asyncio.sleep(0.01)


def test_what_the_model_prints_reaches_the_log_exchange(tmp_path: Path) -> None:
    async def scenario() -> None:
        publisher = FakePublisher()
        worker, model = await a_worker(tmp_path, publisher, FakeStorage(tmp_path), mode="talks")
        try:
            await worker.handle_start(work(a_start()))
            await until(lambda: len(publisher.logs()) >= 3, "the model's output")

            printed = {log.message: log for log in publisher.logs()}
            assert "transcribing staff 1/2" in printed
            assert "staff 2 is smudged" in printed

            # Attributed to the Pipeline Execution that caused the work, which
            # rode along on the request precisely so that the Model need not
            # know about it.
            line = printed["transcribing staff 1/2"]
            assert line.pipeline_execution == PipelineExecutionRef(page_id=PAGE_ID, execution_id=1)
            assert line.source.kind == "worker"
            assert line.source.name == "fake-model"
            assert line.source.instance_id == "w-1"
            assert line.timestamp is not None

            # stdout is ordinary output; stderr is where a model complains.
            assert printed["transcribing staff 1/2"].level == "info"
            assert printed["staff 2 is smudged"].level == "warning"
        finally:
            await model.shutdown()

    run(scenario)


def test_the_files_the_model_wrote_are_said_in_the_log(tmp_path: Path) -> None:
    async def scenario() -> None:
        publisher = FakePublisher()
        worker, model = await a_worker(tmp_path, publisher, FakeStorage(tmp_path))
        try:
            await worker.handle_start(work(a_start()))

            assert [log.message for log in publisher.logs()] == ["wrote out.txt"]
        finally:
            await model.shutdown()

    run(scenario)


def test_a_model_failure_is_said_in_the_log_as_well_as_in_the_result(tmp_path: Path) -> None:
    async def scenario() -> None:
        publisher = FakePublisher()
        worker, model = await a_worker(tmp_path, publisher, FakeStorage(tmp_path), mode="fail")
        try:
            await worker.handle_start(work(a_start()))

            [line] = publisher.logs()
            assert line.message == "No staves found in the image."
            assert line.level == "error"
        finally:
            await model.shutdown()

    run(scenario)


def test_output_printed_while_nothing_runs_belongs_to_nobody(tmp_path: Path) -> None:
    """A model announcing itself at startup, or a library printing a banner on
    import, has no execution to be attributed to — so it stays in this head's
    own log and is not published."""

    async def scenario() -> None:
        publisher = FakePublisher()
        worker, model = await a_worker(tmp_path, publisher, FakeStorage(tmp_path))
        assert worker.description.name == "fake-model"
        try:
            # The fake model prints as soon as it is ready; give the reader time
            # to have done something with it, if it were going to.
            await asyncio.sleep(0.1)

            assert publisher.logs() == []
        finally:
            await model.shutdown()

    run(scenario)


def test_a_broker_that_refuses_a_log_line_does_not_fail_the_execution(tmp_path: Path) -> None:
    class RefusingPublisher(FakePublisher):
        async def publish(self, exchange: str, *args: Any, **kwargs: Any) -> None:
            if exchange == LOGS_EXCHANGE:
                raise ConnectionError("the broker went away")
            await super().publish(exchange, *args, **kwargs)

    async def scenario() -> None:
        publisher = RefusingPublisher()
        worker, model = await a_worker(tmp_path, publisher, FakeStorage(tmp_path), mode="talks")
        try:
            await worker.handle_start(work(a_start()))

            # The User loses a line of output, which is worth far less than the
            # work; the execution is reported exactly as it would have been.
            [result] = publisher.results()
            assert result.state == "completed"
        finally:
            await model.shutdown()

    run(scenario)


def test_the_result_is_valid_json_on_the_wire(tmp_path: Path) -> None:
    async def scenario() -> None:
        publisher = FakePublisher()
        worker, model = await a_worker(tmp_path, publisher, FakeStorage(tmp_path))
        try:
            await worker.handle_start(work(a_start()))

            [message] = [m for m in publisher.published if m.exchange == DEFAULT_EXCHANGE]
            assert json.loads(message.body)["type"] == "model-execution-result"
        finally:
            await model.shutdown()

    run(scenario)
