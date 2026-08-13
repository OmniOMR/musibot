"""The result stream: which of my pages have finished.

The one stream scoped to a *User* rather than a page, because that is who wants
it — a client holding twenty pages in flight wants one connection, not twenty.
Driven as raw ASGI (see `tests/streaming.py`), like the other two.
"""

import asyncio
from datetime import UTC, datetime, timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from musibot.core.execution import (
    OrchestratorRef,
    PipelineExecutionResult,
)
from musibot.core.execution import serialize_message as serialize_execution_message

from musibot.api.discovery import ProviderRegistry
from musibot.api.domain import MusicorpusPage, MusicorpusPageRepository
from musibot.api.executions import ExecutionService
from musibot.api.public import PublicAccess
from musibot.api.results import ExecutionResult, ResultHub, ResultSubscription
from musibot.api.routes import streaming as streaming_route
from tests.conftest import ALICE_TOKEN, BOB_TOKEN, ClientBuilder
from tests.streaming import Stream, run
from tests.test_discovery import orchestrator_announcement

PATH = "/pipeline-execution-results"


def hub_of(app: FastAPI) -> ResultHub:
    hub: ResultHub = app.state.results
    return hub


def result_stream(app: FastAPI, token: str = ALICE_TOKEN) -> Stream:
    return Stream(app, PATH, token)


def a_page(repository: MusicorpusPageRepository, owner: str = "alice") -> MusicorpusPage:
    return repository.create(owner)


def a_result(page: MusicorpusPage) -> bytes:
    """What an *Orchestrator* publishes when a pipeline ends."""
    [execution] = page.executions.values()
    return serialize_execution_message(
        PipelineExecutionResult(
            page_id=page.page_id,
            execution_id=execution.execution_id,
            state="completed",
            orchestrator=OrchestratorRef(name="reference", instance_id="3xQ7nP2vKm9w"),
        )
    )


# --- the endpoint ------------------------------------------------------------


def test_an_ended_execution_reaches_its_owner(
    app: FastAPI, repository: MusicorpusPageRepository
) -> None:
    async def scenario() -> None:
        page = a_page(repository)
        execution = page.add_execution("hello-world", "1.0.0", ["image.jpg"], {})

        async with result_stream(app) as stream:
            assert stream.status == 200
            execution.state = "completed"
            hub_of(app).publish(page.owner, page.page_id, execution)

            assert await stream.next_event() == {
                "page_id": page.page_id,
                "execution": {
                    "execution_id": execution.execution_id,
                    "pipeline_name": "hello-world",
                    "pipeline_version": "1.0.0",
                    "input": ["image.jpg"],
                    "state": "completed",
                    "error": None,
                },
            }

    run(scenario)


def test_a_result_carries_the_state_it_had_when_it_settled(
    app: FastAPI, repository: MusicorpusPageRepository
) -> None:
    """A snapshot, not the domain object: a result waiting in a queue must not
    describe a state its execution reached afterwards."""

    async def scenario() -> None:
        page = a_page(repository)
        execution = page.add_execution("hello-world", "1.0.0", ["image.jpg"], {})

        async with result_stream(app) as stream:
            execution.state = "failed"
            execution.error = "no staves found"
            hub_of(app).publish(page.owner, page.page_id, execution)

            # Whatever happens to the execution now — a second run of the page
            # reusing the object, a later correction — the event is already what
            # it was.
            execution.state = "completed"
            execution.error = None

            event = await stream.next_event()
            assert event["execution"]["state"] == "failed"
            assert event["execution"]["error"] == "no staves found"

    run(scenario)


def test_another_identitys_executions_are_not_carried(
    app: FastAPI, repository: MusicorpusPageRepository
) -> None:
    async def scenario() -> None:
        theirs = a_page(repository, owner="bob")
        execution = theirs.add_execution("hello-world", "1.0.0", ["image.jpg"], {})

        async with result_stream(app, ALICE_TOKEN) as stream:
            hub_of(app).publish(theirs.owner, theirs.page_id, execution)

            with pytest.raises(TimeoutError):
                await stream.next_frame(timeout=0.2)

    run(scenario)


def test_two_holders_of_one_token_share_a_stream(
    app: FastAPI, repository: MusicorpusPageRepository
) -> None:
    """Musibot has no sessions: a *Library* token is one identity however many
    people hold it, so a page one of them created is announced to both. A client
    watches for the page IDs it created — which it already tracks — and ignores
    the rest. See `docs/http-api.md`."""

    async def scenario() -> None:
        # The page the *other* holder of alice's token created.
        theirs = a_page(repository, owner="alice")
        execution = theirs.add_execution("hello-world", "1.0.0", ["image.jpg"], {})

        async with result_stream(app, ALICE_TOKEN) as stream:
            hub_of(app).publish(theirs.owner, theirs.page_id, execution)

            assert (await stream.next_event())["page_id"] == theirs.page_id

    run(scenario)


def test_an_idle_stream_is_kept_alive(app: FastAPI, monkeypatch: pytest.MonkeyPatch) -> None:
    async def scenario() -> None:
        monkeypatch.setattr(streaming_route, "KEEPALIVE_SECONDS", 0.05)

        async with result_stream(app) as stream:
            assert await stream.next_frame() == ": ping\n\n"

    run(scenario)


def test_a_client_that_hangs_up_stops_being_watched(app: FastAPI) -> None:
    async def scenario() -> None:
        async with result_stream(app):
            assert hub_of(app).is_watched("alice")

        await asyncio.sleep(0)
        assert not hub_of(app).is_watched("alice")

    run(scenario)


def test_watching_needs_a_token(client: TestClient) -> None:
    assert client.post(PATH).status_code == 401


def test_each_identity_is_watched_separately(
    app: FastAPI, repository: MusicorpusPageRepository
) -> None:
    async def scenario() -> None:
        mine = a_page(repository, owner="alice")
        execution = mine.add_execution("hello-world", "1.0.0", ["image.jpg"], {})

        async with (
            result_stream(app, ALICE_TOKEN) as alice,
            result_stream(app, BOB_TOKEN) as bob,
        ):
            hub_of(app).publish("alice", mine.page_id, execution)

            assert (await alice.next_event())["page_id"] == mine.page_id
            with pytest.raises(TimeoutError):
                await bob.next_frame(timeout=0.2)

    run(scenario)


# --- what settles an execution ------------------------------------------------


def test_a_result_off_rabbitmq_is_announced(
    app: FastAPI, repository: MusicorpusPageRepository, registry: ProviderRegistry
) -> None:
    """The whole path: an *Orchestrator* reports, this service settles the
    execution, and whoever is watching that identity hears about it."""

    async def scenario() -> None:
        registry.record(orchestrator_announcement())
        executions: ExecutionService = app.state.executions
        page = a_page(repository)

        async with result_stream(app) as stream:
            await executions.start(page, "hello-world", "1.0.0", ["image.jpg"], {})
            await executions.handle_result(a_result(page))

            event = await stream.next_event()
            assert event["page_id"] == page.page_id
            assert event["execution"]["state"] == "completed"

        await executions.shutdown()

    run(scenario)


def test_a_timeout_is_announced_too(
    app: FastAPI, repository: MusicorpusPageRepository, registry: ProviderRegistry
) -> None:
    """The ending a client waiting on a page most needs to hear about, since
    nothing else is ever going to arrive for it."""

    async def scenario() -> None:
        registry.record(orchestrator_announcement())
        executions: ExecutionService = app.state.executions
        page = a_page(repository)

        async with result_stream(app) as stream:
            await executions.start(
                page, "hello-world", "1.0.0", ["image.jpg"], {}, timeout_seconds=0.05
            )

            event = await stream.next_event()
            assert event["execution"]["state"] == "failed"
            assert "timed out" in event["execution"]["error"]

        await executions.shutdown()

    run(scenario)


def test_a_start_is_not_announced(
    app: FastAPI, repository: MusicorpusPageRepository, registry: ProviderRegistry
) -> None:
    """A *result* is by definition an ending: `running` is a state this service
    tracks and never one it reports here."""

    async def scenario() -> None:
        registry.record(orchestrator_announcement())
        executions: ExecutionService = app.state.executions
        page = a_page(repository)

        async with result_stream(app) as stream:
            await executions.start(page, "hello-world", "1.0.0", ["image.jpg"], {})

            with pytest.raises(TimeoutError):
                await stream.next_frame(timeout=0.2)

        await executions.shutdown()

    run(scenario)


# --- the hub itself ----------------------------------------------------------


def test_a_result_nobody_is_watching_is_dropped(repository: MusicorpusPageRepository) -> None:
    page = a_page(repository)
    execution = page.add_execution("hello-world", "1.0.0", ["image.jpg"], {})
    hub = ResultHub()

    hub.publish(page.owner, page.page_id, execution)

    assert not hub.is_watched(page.owner)


def test_a_watcher_that_falls_behind_is_marked_for_disconnection() -> None:
    """Losing a result quietly would send a client waiting on a page down a
    path it has no way to notice, so it is disconnected instead and reconciles
    on reconnect."""
    subscription = ResultSubscription("alice", queue_size=2)
    execution = MusicorpusPage(page_id="7Kf2mP9xLwQa", owner="alice").add_execution(
        "hello-world", "1.0.0", ["image.jpg"], {}
    )

    for _ in range(3):
        subscription.offer(ExecutionResult(page_id="7Kf2mP9xLwQa", execution=execution))

    assert subscription.overrun


def test_a_stream_whose_watcher_fell_behind_is_closed(
    app: FastAPI, repository: MusicorpusPageRepository, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def scenario() -> None:
        monkeypatch.setattr(streaming_route, "KEEPALIVE_SECONDS", 0.05)
        page = a_page(repository)
        execution = page.add_execution("hello-world", "1.0.0", ["image.jpg"], {})

        async with result_stream(app) as stream:
            await stream.next_frame()  # a ping, so the stream is certainly up
            for subscription in hub_of(app)._watchers.of("alice"):
                subscription.overrun = True
            hub_of(app).publish("alice", page.page_id, execution)

            assert await stream.is_finished()

    run(scenario)


# --- public sessions ----------------------------------------------------------


def test_an_expired_public_sessions_stream_ends(
    build_client: ClientBuilder, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Its pages are swept away and nothing further can ever arrive, so the
    connection would otherwise be held until the browser gave up."""

    async def scenario(app: FastAPI, token: str, public: PublicAccess) -> None:
        monkeypatch.setattr(streaming_route, "KEEPALIVE_SECONDS", 0.05)

        async with Stream(app, PATH, token) as stream:
            # Opened while the session was still good, as a visitor's browser
            # does; the hour runs out while they are watching.
            assert stream.status == 200
            await stream.next_frame()  # a ping, so the stream is certainly up

            public._sessions[token].expires_at = datetime.now(UTC) - timedelta(seconds=1)
            await public._expire_sessions()

            assert await stream.is_finished()

    with build_client(public_access_enabled=True) as client:
        app: FastAPI = client.app  # type: ignore[assignment]
        token = client.post("/public-sessions").json()["token"]
        asyncio.run(scenario(app, token, app.state.public_access))
