"""The log stream: what reaches a *User* watching a page being read.

The endpoint is driven as raw ASGI (see `tests/streaming.py`) rather than
through `TestClient`, because a stream that never ends is what a buffering test
client cannot read.
"""

import asyncio

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from musibot.core.execution import ModelExecutionResult, PipelineExecutionRef, WorkerRef
from musibot.core.execution import serialize_message as serialize_execution_message
from musibot.core.logs import LogMessage, LogSource
from musibot.core.logs import serialize_message as serialize_log_message

from musibot.api.discovery import ProviderRegistry
from musibot.api.domain import MusicorpusPageRepository
from musibot.api.executions import ExecutionService
from musibot.api.logs import LogHub, LogLine, LogSubscription
from musibot.api.routes import streaming as streaming_route
from tests.conftest import ALICE_TOKEN
from tests.streaming import Stream, run
from tests.test_discovery import worker_announcement


def hub_of(app: FastAPI) -> LogHub:
    hub: LogHub = app.state.logs
    return hub


def log_stream(app: FastAPI, page_id: str, token: str = ALICE_TOKEN) -> Stream:
    return Stream(app, f"/musicorpus-pages/{page_id}/logs", token)


def a_page(repository: MusicorpusPageRepository, owner: str = "alice") -> tuple[str, int]:
    """A page with one running execution, as a started pipeline leaves it."""
    page = repository.create(owner)
    execution = page.add_execution("hello-world", "1.0.0", ["image.jpg"], {})
    return page.page_id, execution.execution_id


# --- the endpoint ------------------------------------------------------------


def test_a_published_line_reaches_a_watcher(
    app: FastAPI, repository: MusicorpusPageRepository
) -> None:
    async def scenario() -> None:
        page_id, execution_id = a_page(repository)

        async with log_stream(app, page_id) as stream:
            assert stream.status == 200
            assert stream.headers["content-type"].startswith("text/event-stream")
            # Said again for any proxy that is not the nginx in front of this,
            # since a buffered stream arrives all at once, at the end.
            assert stream.headers["x-accel-buffering"] == "no"

            hub_of(app).publish(page_id, execution_id, "transcribing staff 3/12")

            line = await stream.next_event()
            assert line["message"] == "transcribing staff 3/12"
            assert line["execution_id"] == execution_id
            assert line["kind"] == "api"
            assert line["level"] == "info"
            # Time into the execution, not a time of day.
            assert 0 <= line["seconds"] < 5

    run(scenario)


def test_a_line_off_the_exchange_reaches_a_watcher(
    app: FastAPI, repository: MusicorpusPageRepository
) -> None:
    """The path a *Model's* `print` actually takes: *Worker* → RabbitMQ → here."""

    async def scenario() -> None:
        page_id, execution_id = a_page(repository)

        async with log_stream(app, page_id) as stream:
            await hub_of(app).handle_message(
                serialize_log_message(
                    LogMessage(
                        pipeline_execution=PipelineExecutionRef(
                            page_id=page_id, execution_id=execution_id
                        ),
                        source=LogSource(
                            kind="worker", name="staff-detector", instance_id="8Lw4tR6yBn1c"
                        ),
                        level="warning",
                        message="staff 3 is smudged",
                    )
                )
            )

            line = await stream.next_event()
            assert line == {
                "execution_id": execution_id,
                "seconds": line["seconds"],
                "kind": "worker",
                "source": "staff-detector",
                "level": "warning",
                "message": "staff 3 is smudged",
            }

    run(scenario)


def test_two_watchers_of_one_page_both_see_a_line(
    app: FastAPI, repository: MusicorpusPageRepository
) -> None:
    async def scenario() -> None:
        page_id, execution_id = a_page(repository)

        async with (
            log_stream(app, page_id) as one,
            log_stream(app, page_id) as two,
        ):
            hub_of(app).publish(page_id, execution_id, "hello")

            assert (await one.next_event())["message"] == "hello"
            assert (await two.next_event())["message"] == "hello"

    run(scenario)


def test_a_watcher_hears_nothing_about_another_page(
    app: FastAPI, repository: MusicorpusPageRepository
) -> None:
    async def scenario() -> None:
        watched, _ = a_page(repository)
        other, other_execution = a_page(repository)

        async with log_stream(app, watched) as stream:
            hub_of(app).publish(other, other_execution, "not your business")

            with pytest.raises(TimeoutError):
                await stream.next_frame(timeout=0.2)

    run(scenario)


def test_an_idle_stream_is_kept_alive(
    app: FastAPI, repository: MusicorpusPageRepository, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Something has to travel down an idle connection, or a proxy closes it —
    and a *Pipeline* waiting to be picked up is silent for as long as that
    takes."""

    async def scenario() -> None:
        monkeypatch.setattr(streaming_route, "KEEPALIVE_SECONDS", 0.05)
        page_id, _ = a_page(repository)

        async with log_stream(app, page_id) as stream:
            assert await stream.next_frame() == ": ping\n\n"

    run(scenario)


def test_the_stream_ends_when_the_page_is_deleted(
    app: FastAPI, repository: MusicorpusPageRepository, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Nothing further can ever arrive for a deleted page, and its watcher would
    otherwise hold a connection open until the browser gave up."""

    async def scenario() -> None:
        monkeypatch.setattr(streaming_route, "KEEPALIVE_SECONDS", 0.05)
        page_id, _ = a_page(repository)

        async with log_stream(app, page_id) as stream:
            await stream.next_frame()  # a ping, so the stream is certainly up
            repository.delete(page_id)

            assert await stream.is_finished()

    run(scenario)


def test_a_client_that_hangs_up_stops_being_watched(
    app: FastAPI, repository: MusicorpusPageRepository
) -> None:
    async def scenario() -> None:
        page_id, _ = a_page(repository)

        async with log_stream(app, page_id):
            assert hub_of(app).is_watched(page_id)

        # Leaving the block is the client disconnecting. Forgetting to
        # unsubscribe here is how a departed client goes on being fed forever.
        await asyncio.sleep(0)
        assert not hub_of(app).is_watched(page_id)

    run(scenario)


# --- who may watch -----------------------------------------------------------
#
# Answered before a byte of stream, so an ordinary client works.


def test_another_users_page_cannot_be_watched(client: TestClient, bob: dict[str, str]) -> None:
    page_id = client.post(
        "/musicorpus-pages", headers={"Authorization": f"Bearer {ALICE_TOKEN}"}
    ).json()["page_id"]

    response = client.post(f"/musicorpus-pages/{page_id}/logs", headers=bob)

    # A 404 rather than a 403, as everywhere else: a caller must not be able to
    # tell a page they cannot see from one that does not exist.
    assert response.status_code == 404


def test_watching_needs_a_token(client: TestClient) -> None:
    response = client.post("/musicorpus-pages/7Kf2mP9xLwQa/logs")

    assert response.status_code == 401


def test_watching_a_page_that_does_not_exist_is_a_404(
    client: TestClient, alice: dict[str, str]
) -> None:
    assert client.post("/musicorpus-pages/7Kf2mP9xLwQa/logs", headers=alice).status_code == 404


# --- the hub itself ----------------------------------------------------------


def test_a_line_nobody_is_watching_is_dropped(repository: MusicorpusPageRepository) -> None:
    """The common case: every *Worker* in the fleet publishes whether or not
    anybody is reading, and this is where that stops."""
    page_id, execution_id = a_page(repository)
    hub = LogHub(repository)

    hub.publish(page_id, execution_id, "into the void")

    assert not hub.is_watched(page_id)


def test_a_line_for_an_unknown_execution_is_dropped(repository: MusicorpusPageRepository) -> None:
    async def scenario() -> None:
        page_id, _ = a_page(repository)
        hub = LogHub(repository)

        with hub.subscribe(page_id) as subscription:
            hub.publish(page_id, 99, "from a Worker still running after a page was deleted")

            assert await subscription.next_line(timeout=0.05) is None

    run(scenario)


def test_an_unintelligible_message_does_not_wedge_the_consumer(
    repository: MusicorpusPageRepository,
) -> None:
    async def scenario() -> None:
        page_id, execution_id = a_page(repository)
        hub = LogHub(repository)

        with hub.subscribe(page_id) as subscription:
            await hub.handle_message(b'{"type": "progress", "fraction": 0.5}')
            hub.publish(page_id, execution_id, "still going")

            line = await subscription.next_line(timeout=0.05)
            assert line is not None and line.message == "still going"

    run(scenario)


def test_a_watcher_that_cannot_keep_up_is_told_what_it_missed() -> None:
    """A silent hole in a log is worse than one that admits to the hole."""

    async def scenario() -> None:
        subscription = LogSubscription("7Kf2mP9xLwQa", queue_size=2)
        for index in range(5):
            subscription.offer(
                LogLine(
                    execution_id=1,
                    seconds=0.0,
                    kind="worker",
                    source="staff-detector",
                    level="info",
                    message=f"line {index}",
                )
            )

        first = await subscription.next_line(timeout=0.05)
        assert first is not None
        assert "3 line(s) dropped" in first.message
        assert first.level == "warning"

        # And what did fit is still there, in order.
        assert [
            (await subscription.next_line(timeout=0.05)).message  # type: ignore[union-attr]
            for _ in range(2)
        ] == ["line 0", "line 1"]

    run(scenario)


# --- what the service says for itself ----------------------------------------


def test_the_service_says_when_an_execution_starts_and_finishes(
    app: FastAPI, repository: MusicorpusPageRepository, registry: ProviderRegistry
) -> None:
    """A *Model* that prints nothing still leaves a log worth reading, because
    the moments only this service knows about are in it."""

    async def scenario() -> None:
        page = repository.create("alice")
        registry.record(worker_announcement())
        executions: ExecutionService = app.state.executions

        async with log_stream(app, page.page_id) as stream:
            execution = await executions.start(
                page, "staff-detector", "2026-07-22", ["image.jpg"], {}
            )
            started = await stream.next_event()
            assert started["message"] == "running staff-detector 2026-07-22 on image.jpg"
            assert started["kind"] == "api"

            await executions.handle_model_result(a_completion(executions))
            finished = await stream.next_event()
            assert finished["message"].startswith("completed in ")
            assert finished["execution_id"] == execution.execution_id

        await executions.shutdown()

    run(scenario)


def a_completion(executions: ExecutionService) -> bytes:
    """The result of the one *Model* run standing in for an *ImplicitPipeline*."""
    [model_execution_id] = list(executions._model_executions)
    return serialize_execution_message(
        ModelExecutionResult(
            model_execution_id=model_execution_id,
            state="completed",
            worker=WorkerRef(name="staff-detector", instance_id="worker-1"),
        )
    )
