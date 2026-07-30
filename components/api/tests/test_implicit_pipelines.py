"""*ImplicitPipelines*: the `api` service running one *Model* by itself.

There is no *Orchestrator* anywhere in these tests, which is the point — a
*Model* must be executable with none deployed.
"""

import asyncio

from musibot.core.discovery import Signature
from musibot.core.execution import (
    MODEL_EXECUTION_CONTROL_EXCHANGE,
    MODEL_EXECUTIONS_EXCHANGE,
    PIPELINE_EXECUTION_CONTROL_EXCHANGE,
    PIPELINE_EXECUTIONS_EXCHANGE,
    ExecutionState,
    ModelExecutionResult,
    ModelExecutionStart,
    ModelExecutionTerminate,
    WorkerRef,
    parse_model_execution_message,
    routing_key,
    serialize_message,
)
from musibot.core.patterns import SignatureMismatch

from musibot.api.discovery import ProviderRegistry
from musibot.api.domain import MusicorpusPageRepository
from musibot.api.executions import ExecutionService, PipelineNotFound
from tests.fakes import FakePublisher
from tests.test_discovery import orchestrator_announcement, worker_announcement

MODEL = ("staff-detector", "2026-07-22")


def a_registry_with_the_model() -> ProviderRegistry:
    registry = ProviderRegistry()
    registry.record(worker_announcement())
    return registry


def a_service(
    repository: MusicorpusPageRepository,
    publisher: FakePublisher,
    registry: ProviderRegistry,
    *,
    timeout_seconds: float = 300,
) -> ExecutionService:
    return ExecutionService(
        repository, publisher, registry, timeout_seconds=timeout_seconds, instance_id="api-1"
    )


def a_model_result(
    model_execution_id: str, state: ExecutionState, error: str | None = None
) -> bytes:
    return serialize_message(
        ModelExecutionResult(
            model_execution_id=model_execution_id,
            state=state,
            error=error,
            worker=WorkerRef(name="staff-detector", instance_id="8Lw4tR6yBn1c"),
        )
    )


def test_starting_a_model_dispatches_a_model_execution() -> None:
    async def scenario() -> None:
        repository = MusicorpusPageRepository()
        publisher = FakePublisher()
        page = repository.create("alice")
        service = a_service(repository, publisher, a_registry_with_the_model())

        execution = await service.start(page, *MODEL, ["image.jpg"], {"threshold": 0.5})

        assert execution.state == "running"
        message = publisher.only(MODEL_EXECUTIONS_EXCHANGE)
        assert message.routing_key == routing_key(*MODEL)
        assert message.expiration_seconds == 300
        # The result comes back to this service's own queue, named on the
        # request — nothing else could tell a Worker where to answer.
        assert message.reply_to == service.reply_queue

        start = parse_model_execution_message(message.body)
        assert isinstance(start, ModelExecutionStart)
        assert message.correlation_id == start.model_execution_id
        assert start.page_id == page.page_id
        assert start.parameters == {"threshold": 0.5}
        # The Files the User named, passed straight through — this service does
        # not expand the Model's Signature to arrive at them.
        assert start.input == ["image.jpg"]
        # Rides along so a Worker can attribute its logs without asking anyone.
        assert start.pipeline_execution.page_id == page.page_id
        assert start.pipeline_execution.execution_id == execution.execution_id

        # No Orchestrator was involved at any point.
        assert all(m.exchange != PIPELINE_EXECUTIONS_EXCHANGE for m in publisher.published)

        await service.shutdown()

    asyncio.run(scenario())


def test_a_model_result_completes_the_pipeline_execution() -> None:
    async def scenario() -> None:
        repository = MusicorpusPageRepository()
        publisher = FakePublisher()
        page = repository.create("alice")
        service = a_service(repository, publisher, a_registry_with_the_model())
        execution = await service.start(page, *MODEL, ["image.jpg"], {})

        start = parse_model_execution_message(publisher.only(MODEL_EXECUTIONS_EXCHANGE).body)
        assert isinstance(start, ModelExecutionStart)
        await service.handle_model_result(a_model_result(start.model_execution_id, "completed"))

        assert page.executions[execution.execution_id].state == "completed"
        await service.shutdown()

    asyncio.run(scenario())


def test_a_failed_model_fails_the_pipeline_execution_with_its_error() -> None:
    async def scenario() -> None:
        repository = MusicorpusPageRepository()
        publisher = FakePublisher()
        page = repository.create("alice")
        service = a_service(repository, publisher, a_registry_with_the_model())
        execution = await service.start(page, *MODEL, ["image.jpg"], {})

        start = parse_model_execution_message(publisher.only(MODEL_EXECUTIONS_EXCHANGE).body)
        assert isinstance(start, ModelExecutionStart)
        await service.handle_model_result(
            a_model_result(start.model_execution_id, "failed", "No staves found in the image.")
        )

        settled = page.executions[execution.execution_id]
        assert settled.state == "failed"
        assert settled.error == "No staves found in the image."
        await service.shutdown()

    asyncio.run(scenario())


def test_a_result_for_an_unknown_model_execution_is_ignored() -> None:
    async def scenario() -> None:
        service = a_service(MusicorpusPageRepository(), FakePublisher(), ProviderRegistry())

        # Must not raise: a result may outlive the execution it belonged to.
        await service.handle_model_result(a_model_result("8Lw4tR6yBn1c", "completed"))
        await service.shutdown()

    asyncio.run(scenario())


def test_a_timed_out_implicit_pipeline_terminates_the_model_execution() -> None:
    async def scenario() -> None:
        repository = MusicorpusPageRepository()
        publisher = FakePublisher()
        page = repository.create("alice")
        service = a_service(
            repository, publisher, a_registry_with_the_model(), timeout_seconds=0.05
        )

        execution = await service.start(page, *MODEL, ["image.jpg"], {})
        start = parse_model_execution_message(publisher.only(MODEL_EXECUTIONS_EXCHANGE).body)
        assert isinstance(start, ModelExecutionStart)

        await asyncio.sleep(0.2)

        settled = page.executions[execution.execution_id]
        assert settled.state == "failed"
        assert "timed out" in (settled.error or "")

        # This service is the orchestrator here, so it cancels the Worker
        # directly rather than telling orchestrators that do not exist.
        terminate = parse_model_execution_message(
            publisher.only(MODEL_EXECUTION_CONTROL_EXCHANGE).body
        )
        assert isinstance(terminate, ModelExecutionTerminate)
        assert terminate.model_execution_id == start.model_execution_id
        assert all(m.exchange != PIPELINE_EXECUTION_CONTROL_EXCHANGE for m in publisher.published)

        await service.shutdown()

    asyncio.run(scenario())


def test_a_result_arriving_after_the_timeout_is_ignored() -> None:
    async def scenario() -> None:
        repository = MusicorpusPageRepository()
        publisher = FakePublisher()
        page = repository.create("alice")
        service = a_service(
            repository, publisher, a_registry_with_the_model(), timeout_seconds=0.05
        )

        execution = await service.start(page, *MODEL, ["image.jpg"], {})
        start = parse_model_execution_message(publisher.only(MODEL_EXECUTIONS_EXCHANGE).body)
        assert isinstance(start, ModelExecutionStart)

        await asyncio.sleep(0.2)
        await service.handle_model_result(a_model_result(start.model_execution_id, "completed"))

        assert page.executions[execution.execution_id].state == "failed"
        await service.shutdown()

    asyncio.run(scenario())


def test_deleting_a_page_terminates_a_running_model_execution() -> None:
    async def scenario() -> None:
        repository = MusicorpusPageRepository()
        publisher = FakePublisher()
        page = repository.create("alice")
        service = a_service(repository, publisher, a_registry_with_the_model())

        await service.start(page, *MODEL, ["image.jpg"], {})
        publisher.published.clear()
        await service.terminate_running(page)

        terminate = parse_model_execution_message(
            publisher.only(MODEL_EXECUTION_CONTROL_EXCHANGE).body
        )
        assert isinstance(terminate, ModelExecutionTerminate)
        await service.shutdown()

    asyncio.run(scenario())


def test_a_slotted_model_is_run_over_the_instance_the_user_named() -> None:
    async def scenario() -> None:
        repository = MusicorpusPageRepository()
        publisher = FakePublisher()
        page = repository.create("alice")
        registry = ProviderRegistry()
        registry.record(
            worker_announcement(
                signature=Signature(
                    input=["Staves/{s}/image.jpg"],
                    output=["Staves/{s}/transcription.musicxml"],
                )
            )
        )
        service = a_service(repository, publisher, registry)

        await service.start(page, *MODEL, ["Staves/7/image.jpg"], {})

        start = parse_model_execution_message(publisher.only(MODEL_EXECUTIONS_EXCHANGE).body)
        assert isinstance(start, ModelExecutionStart)
        assert start.input == ["Staves/7/image.jpg"]

        await service.shutdown()

    asyncio.run(scenario())


def test_an_input_list_the_model_signature_does_not_admit_is_refused() -> None:
    async def scenario() -> None:
        repository = MusicorpusPageRepository()
        publisher = FakePublisher()
        page = repository.create("alice")
        registry = ProviderRegistry()
        registry.record(
            worker_announcement(
                signature=Signature(
                    input=["Staves/{s}/image.jpg"],
                    output=["Staves/{s}/transcription.musicxml"],
                )
            )
        )
        service = a_service(repository, publisher, registry)

        # A whole page of staves handed to a one-staff Model.
        try:
            await service.start(page, *MODEL, ["Staves/1/image.jpg", "Staves/2/image.jpg"], {})
        except SignatureMismatch:
            pass
        else:
            raise AssertionError("expected SignatureMismatch")

        # Refused before the execution existed, so the page is untouched.
        assert publisher.published == []
        assert page.executions == {}
        await service.shutdown()

    asyncio.run(scenario())


def test_a_pipeline_nobody_announces_is_refused() -> None:
    async def scenario() -> None:
        repository = MusicorpusPageRepository()
        publisher = FakePublisher()
        page = repository.create("alice")
        service = a_service(repository, publisher, ProviderRegistry())

        try:
            await service.start(page, "nothing-like-this", "1.0.0", ["image.jpg"], {})
        except PipelineNotFound:
            pass
        else:
            raise AssertionError("expected PipelineNotFound")

        # Nothing was dispatched and no execution was recorded for the page.
        assert publisher.published == []
        assert page.executions == {}
        await service.shutdown()

    asyncio.run(scenario())


def test_an_explicit_pipeline_wins_over_a_colliding_model() -> None:
    async def scenario() -> None:
        repository = MusicorpusPageRepository()
        publisher = FakePublisher()
        registry = ProviderRegistry()
        registry.record(orchestrator_announcement(pipeline_name=MODEL[0], version=MODEL[1]))
        registry.record(worker_announcement())
        page = repository.create("alice")
        service = a_service(repository, publisher, registry)

        await service.start(page, *MODEL, ["image.jpg"], {})

        # Matching the listing, where the colliding ImplicitPipeline is the one
        # suppressed.
        assert publisher.only(PIPELINE_EXECUTIONS_EXCHANGE).routing_key == routing_key(*MODEL)
        assert all(m.exchange != MODEL_EXECUTIONS_EXCHANGE for m in publisher.published)
        await service.shutdown()

    asyncio.run(scenario())
