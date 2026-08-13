"""The file-change stream: a *File* shown as it appears rather than at a poll.

Driven as raw ASGI (see `tests/streaming.py`), like the log stream.
"""

import asyncio

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from musibot.core.execution import PipelineExecutionRef
from musibot.core.file_changes import FilesChanged
from musibot.core.file_changes import serialize_message as serialize_file_change_message

from musibot.api.domain import MusicorpusPageRepository
from musibot.api.file_changes import FileChangeHub, FileChangeSubscription
from musibot.api.routes import streaming as streaming_route
from tests.conftest import ALICE_TOKEN
from tests.streaming import Stream, run


def hub_of(app: FastAPI) -> FileChangeHub:
    hub: FileChangeHub = app.state.file_changes
    return hub


def file_change_stream(app: FastAPI, page_id: str, token: str = ALICE_TOKEN) -> Stream:
    return Stream(app, f"/musicorpus-pages/{page_id}/file-changes", token)


def a_page(repository: MusicorpusPageRepository, owner: str = "alice") -> tuple[str, int]:
    """A page with one running execution, as a started pipeline leaves it."""
    page = repository.create(owner)
    execution = page.add_execution("hello-world", "1.0.0", ["image.jpg"], {})
    return page.page_id, execution.execution_id


def a_notice(page_id: str, execution_id: int, *paths: str) -> bytes:
    return serialize_file_change_message(
        FilesChanged(
            pipeline_execution=PipelineExecutionRef(page_id=page_id, execution_id=execution_id),
            paths=list(paths),
        )
    )


# --- the endpoint ------------------------------------------------------------


def test_a_notice_off_the_exchange_reaches_a_watcher(
    app: FastAPI, repository: MusicorpusPageRepository
) -> None:
    """The path a *Worker's* upload actually takes: *Worker* → RabbitMQ → here."""

    async def scenario() -> None:
        page_id, execution_id = a_page(repository)

        async with file_change_stream(app, page_id) as stream:
            assert stream.status == 200
            assert stream.headers["content-type"].startswith("text/event-stream")

            await hub_of(app).handle_message(
                a_notice(page_id, execution_id, "Staves/1/transcription.musicxml", "layout.json")
            )

            assert await stream.next_event() == {
                "execution_id": execution_id,
                "paths": ["Staves/1/transcription.musicxml", "layout.json"],
            }

    run(scenario)


def test_a_watcher_hears_nothing_about_another_page(
    app: FastAPI, repository: MusicorpusPageRepository
) -> None:
    async def scenario() -> None:
        watched, _ = a_page(repository)
        other, other_execution = a_page(repository)

        async with file_change_stream(app, watched) as stream:
            await hub_of(app).handle_message(a_notice(other, other_execution, "layout.json"))

            with pytest.raises(TimeoutError):
                await stream.next_frame(timeout=0.2)

    run(scenario)


def test_an_idle_stream_is_kept_alive(
    app: FastAPI, repository: MusicorpusPageRepository, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def scenario() -> None:
        monkeypatch.setattr(streaming_route, "KEEPALIVE_SECONDS", 0.05)
        page_id, _ = a_page(repository)

        async with file_change_stream(app, page_id) as stream:
            assert await stream.next_frame() == ": ping\n\n"

    run(scenario)


def test_the_stream_ends_when_the_page_is_deleted(
    app: FastAPI, repository: MusicorpusPageRepository, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def scenario() -> None:
        monkeypatch.setattr(streaming_route, "KEEPALIVE_SECONDS", 0.05)
        page_id, _ = a_page(repository)

        async with file_change_stream(app, page_id) as stream:
            await stream.next_frame()  # a ping, so the stream is certainly up
            repository.delete(page_id)

            assert await stream.is_finished()

    run(scenario)


def test_a_client_that_hangs_up_stops_being_watched(
    app: FastAPI, repository: MusicorpusPageRepository
) -> None:
    async def scenario() -> None:
        page_id, _ = a_page(repository)

        async with file_change_stream(app, page_id):
            assert hub_of(app).is_watched(page_id)

        await asyncio.sleep(0)
        assert not hub_of(app).is_watched(page_id)

    run(scenario)


def test_the_log_and_the_file_changes_are_separate_streams(
    app: FastAPI, repository: MusicorpusPageRepository
) -> None:
    """A client that wants to know about a new *File* should not have to read a
    deep-learning library's warnings to find out."""

    async def scenario() -> None:
        page_id, execution_id = a_page(repository)

        async with file_change_stream(app, page_id) as stream:
            app.state.logs.publish(page_id, execution_id, "a great deal of chatter")

            with pytest.raises(TimeoutError):
                await stream.next_frame(timeout=0.2)

    run(scenario)


# --- who may watch -----------------------------------------------------------


def test_another_users_page_cannot_be_watched(client: TestClient, bob: dict[str, str]) -> None:
    page_id = client.post(
        "/musicorpus-pages", headers={"Authorization": f"Bearer {ALICE_TOKEN}"}
    ).json()["page_id"]

    assert client.post(f"/musicorpus-pages/{page_id}/file-changes", headers=bob).status_code == 404


def test_watching_needs_a_token(client: TestClient) -> None:
    assert client.post("/musicorpus-pages/7Kf2mP9xLwQa/file-changes").status_code == 401


# --- the hub itself ----------------------------------------------------------


def test_a_notice_nobody_is_watching_is_dropped(repository: MusicorpusPageRepository) -> None:
    page_id, execution_id = a_page(repository)
    hub = FileChangeHub()

    hub.publish(page_id, execution_id, ["layout.json"])

    assert not hub.is_watched(page_id)


def test_notices_coalesce_while_a_client_is_not_reading() -> None:
    """Two writes of one path between reads are one thing to do about it: list
    the page again. So they arrive as one event naming the path once, and there
    is no queue to overflow."""

    async def scenario() -> None:
        subscription = FileChangeSubscription("7Kf2mP9xLwQa")

        subscription.offer(1, ["layout.json"])
        subscription.offer(1, ["layout.json", "Staves/1/image.jpg"])
        subscription.offer(1, ["Staves/2/image.jpg"])

        changes = await subscription.next_changes(timeout=0.05)

        assert changes is not None
        [change] = changes
        assert change.paths == ["layout.json", "Staves/1/image.jpg", "Staves/2/image.jpg"]

        # And nothing is left behind to be delivered twice.
        assert await subscription.next_changes(timeout=0.05) is None

    run(scenario)


def test_two_executions_are_not_merged_into_one_notice() -> None:
    """Which execution wrote a *File* is knowable at this moment and never
    again, so coalescing keeps them apart."""

    async def scenario() -> None:
        subscription = FileChangeSubscription("7Kf2mP9xLwQa")

        subscription.offer(1, ["layout.json"])
        subscription.offer(2, ["Staves/1/transcription.musicxml"])

        changes = await subscription.next_changes(timeout=0.05)

        assert changes is not None
        assert [(change.execution_id, change.paths) for change in changes] == [
            (1, ["layout.json"]),
            (2, ["Staves/1/transcription.musicxml"]),
        ]

    run(scenario)


def test_an_unintelligible_message_does_not_wedge_the_consumer(
    repository: MusicorpusPageRepository,
) -> None:
    async def scenario() -> None:
        page_id, execution_id = a_page(repository)
        hub = FileChangeHub()

        with hub.subscribe(page_id) as subscription:
            await hub.handle_message(b'{"type": "files-changed", "paths": "not a list"}')
            await hub.handle_message(a_notice(page_id, execution_id, "layout.json"))

            changes = await subscription.next_changes(timeout=0.05)
            assert changes is not None and changes[0].paths == ["layout.json"]

    run(scenario)


def test_an_empty_notice_says_nothing(repository: MusicorpusPageRepository) -> None:
    """A *Worker* does not send one, but a stream that woke a client for no
    paths would be a client refreshing for no reason."""

    async def scenario() -> None:
        page_id, execution_id = a_page(repository)
        hub = FileChangeHub()

        with hub.subscribe(page_id) as subscription:
            await hub.handle_message(a_notice(page_id, execution_id))

            assert await subscription.next_changes(timeout=0.05) is None

    run(scenario)
