"""The ExecutionService, tested directly on the event loop — no HTTP, no broker.

Publishing goes to a FakePublisher that records messages; timeouts use a tiny
budget so the tests do not wait.
"""

import asyncio

from musibot.core.execution import (
    PIPELINE_EXECUTION_CONTROL_EXCHANGE,
    PIPELINE_EXECUTIONS_EXCHANGE,
    ExecutionState,
    OrchestratorRef,
    PipelineExecutionResult,
    PipelineExecutionStart,
    PipelineExecutionTerminate,
    parse_pipeline_execution_message,
    routing_key,
    serialize_message,
)

from musibot.api.domain import MusicorpusPageRepository
from musibot.api.executions import ExecutionService
from tests.fakes import FakePublisher


def a_result(
    page_id: str, execution_id: int, state: ExecutionState, error: str | None = None
) -> bytes:
    return serialize_message(
        PipelineExecutionResult(
            page_id=page_id,
            execution_id=execution_id,
            state=state,
            error=error,
            orchestrator=OrchestratorRef(name="ref", instance_id="3xQ7nP2vKm9w"),
        )
    )


def test_start_publishes_a_start_message() -> None:
    async def scenario() -> None:
        repository = MusicorpusPageRepository()
        publisher = FakePublisher()
        page = repository.create("alice")
        service = ExecutionService(repository, publisher, timeout_seconds=300)

        execution = await service.start(page, "hello-world", "1.0.0", {"x": 1})

        assert execution.state == "running"
        [message] = publisher.published
        assert message.exchange == PIPELINE_EXECUTIONS_EXCHANGE
        assert message.routing_key == routing_key("hello-world", "1.0.0")
        assert message.expiration_seconds == 300

        start = parse_pipeline_execution_message(message.body)
        assert isinstance(start, PipelineExecutionStart)
        assert start.execution_id == execution.execution_id
        assert start.parameters == {"x": 1}

        await service.shutdown()

    asyncio.run(scenario())


def test_a_result_settles_the_execution() -> None:
    async def scenario() -> None:
        repository = MusicorpusPageRepository()
        page = repository.create("alice")
        service = ExecutionService(repository, FakePublisher(), timeout_seconds=300)
        execution = await service.start(page, "p", "1", {})

        await service.handle_result(a_result(page.page_id, execution.execution_id, "completed"))

        assert page.executions[execution.execution_id].state == "completed"
        await service.shutdown()

    asyncio.run(scenario())


def test_a_failed_result_carries_its_error() -> None:
    async def scenario() -> None:
        repository = MusicorpusPageRepository()
        page = repository.create("alice")
        service = ExecutionService(repository, FakePublisher(), timeout_seconds=300)
        execution = await service.start(page, "p", "1", {})

        await service.handle_result(
            a_result(page.page_id, execution.execution_id, "failed", "boom")
        )

        settled = page.executions[execution.execution_id]
        assert settled.state == "failed"
        assert settled.error == "boom"
        await service.shutdown()

    asyncio.run(scenario())


def test_a_late_result_does_not_overturn_a_settled_execution() -> None:
    async def scenario() -> None:
        repository = MusicorpusPageRepository()
        page = repository.create("alice")
        service = ExecutionService(repository, FakePublisher(), timeout_seconds=300)
        execution = await service.start(page, "p", "1", {})

        await service.handle_result(a_result(page.page_id, execution.execution_id, "failed", "x"))
        # A completion that arrives after the failure is ignored.
        await service.handle_result(a_result(page.page_id, execution.execution_id, "completed"))

        assert page.executions[execution.execution_id].state == "failed"
        await service.shutdown()

    asyncio.run(scenario())


def test_a_result_for_an_unknown_page_is_ignored() -> None:
    async def scenario() -> None:
        service = ExecutionService(MusicorpusPageRepository(), FakePublisher(), timeout_seconds=300)

        # A well-formed page ID that was never created: must not raise, just
        # do nothing.
        await service.handle_result(a_result("aaaaaaaaaaaa", 1, "completed"))
        await service.shutdown()

    asyncio.run(scenario())


def test_timeout_fails_the_execution_and_publishes_a_terminate() -> None:
    async def scenario() -> None:
        repository = MusicorpusPageRepository()
        publisher = FakePublisher()
        page = repository.create("alice")
        service = ExecutionService(repository, publisher, timeout_seconds=0.05)

        execution = await service.start(page, "p", "1", {})
        await asyncio.sleep(0.2)

        settled = page.executions[execution.execution_id]
        assert settled.state == "failed"
        assert "timed out" in (settled.error or "")

        terminates = [
            m for m in publisher.published if m.exchange == PIPELINE_EXECUTION_CONTROL_EXCHANGE
        ]
        assert len(terminates) == 1
        terminate = parse_pipeline_execution_message(terminates[0].body)
        assert isinstance(terminate, PipelineExecutionTerminate)
        assert terminate.execution_id == execution.execution_id

        await service.shutdown()

    asyncio.run(scenario())


def test_a_completed_execution_does_not_time_out() -> None:
    async def scenario() -> None:
        repository = MusicorpusPageRepository()
        publisher = FakePublisher()
        page = repository.create("alice")
        service = ExecutionService(repository, publisher, timeout_seconds=0.05)

        execution = await service.start(page, "p", "1", {})
        await service.handle_result(a_result(page.page_id, execution.execution_id, "completed"))
        await asyncio.sleep(0.2)  # let the timer fire on an already-settled execution

        assert page.executions[execution.execution_id].state == "completed"
        # No terminate was published, only the original start.
        assert all(m.exchange != PIPELINE_EXECUTION_CONTROL_EXCHANGE for m in publisher.published)
        await service.shutdown()

    asyncio.run(scenario())


def test_terminate_running_targets_only_running_executions() -> None:
    async def scenario() -> None:
        repository = MusicorpusPageRepository()
        publisher = FakePublisher()
        page = repository.create("alice")
        service = ExecutionService(repository, publisher, timeout_seconds=300)

        done = await service.start(page, "p", "1", {})
        await service.handle_result(a_result(page.page_id, done.execution_id, "completed"))
        running = await service.start(page, "p", "1", {})

        publisher.published.clear()
        await service.terminate_running(page)

        [message] = publisher.published
        terminate = parse_pipeline_execution_message(message.body)
        assert isinstance(terminate, PipelineExecutionTerminate)
        assert terminate.execution_id == running.execution_id

        await service.shutdown()

    asyncio.run(scenario())
