"""The client, driven against a fake Musibot server over a mocked transport."""

import httpx
import pytest

from musibot.client import (
    MusibotApiError,
    MusibotClient,
    PipelineExecutionFailed,
    PipelineExecutionTimedOut,
    PipelineNotAvailable,
)
from tests.fake_server import API_HOST, PAGE_ID, FakeServer

SCAN = b"\xff\xd8\xff\xe0 pretend this is a JPEG"
TRANSCRIPTION = b'<?xml version="1.0"?><score-partwise/>'


def a_client(server: FakeServer) -> MusibotClient:
    return MusibotClient(
        musibot_api_url=API_HOST,
        api_token="secret",
        transport=server.transport(),
        # Nothing here should wait on a wall clock.
        poll_interval_seconds=0,
    )


def test_process_page_round_trip() -> None:
    server = FakeServer(
        stored={f"{PAGE_ID}/transcription.musicxml": TRANSCRIPTION},
    )

    with a_client(server) as client:
        output = client.process_page(
            input={"image.jpg": SCAN},
            pipeline=("hello-model", "1.0.0"),
            output={"transcription.musicxml"},
        )

    assert output == {"transcription.musicxml": TRANSCRIPTION}
    # The scan went straight to object storage, not through the api service.
    assert server.objects[f"{PAGE_ID}/image.jpg"] == SCAN
    # The input list is filled in from what this call uploaded: the server keeps
    # no list of a page's Files and could not have supplied it.
    assert server.started == [
        {
            "pipeline_name": "hello-model",
            "pipeline_version": "1.0.0",
            "input": ["image.jpg"],
            "parameters": {},
        }
    ]
    # And the page was given back once its results were in hand.
    assert server.deleted_pages == [PAGE_ID]


def test_every_api_request_carries_the_token() -> None:
    server = FakeServer(stored={f"{PAGE_ID}/out.txt": b"x"})

    with a_client(server) as client:
        client.process_page(input={}, pipeline=("p", "1"), output={"out.txt"})

    assert server.token == "Bearer secret"
    api_requests = [r for r in server.requests if r.url.host == "musibot.test"]
    assert all("Authorization" in r.headers for r in api_requests)


def test_the_token_never_reaches_object_storage() -> None:
    """The API token authenticates against the `api` service and nothing else.

    A presigned URL signs itself in the query string, and object storage
    refuses a request that also presents an Authorization header — so sending
    it would break every transfer, besides handing the token to another host.
    """
    server = FakeServer(stored={f"{PAGE_ID}/out.txt": b"x"})

    with a_client(server) as client:
        client.process_page(input={"image.jpg": SCAN}, pipeline=("p", "1"), output={"out.txt"})

    storage_requests = [r for r in server.requests if r.url.host == "minio.test"]
    assert storage_requests, "the test proved nothing if no transfer happened"
    assert all("Authorization" not in r.headers for r in storage_requests)


def test_it_waits_while_the_execution_runs() -> None:
    server = FakeServer(
        states=["running", "running", "completed"],
        stored={f"{PAGE_ID}/out.txt": b"x"},
    )

    with a_client(server) as client:
        client.process_page(input={}, pipeline=("p", "1"), output={"out.txt"})

    assert server.polls == 3


def test_a_failed_execution_raises_with_the_reason() -> None:
    server = FakeServer(states=["failed"])

    with a_client(server) as client, pytest.raises(PipelineExecutionFailed) as raised:
        client.process_page(input={"image.jpg": SCAN}, pipeline=("p", "1"), output={"out.txt"})

    assert raised.value.error == "No staves found in the image."
    assert raised.value.page_id == PAGE_ID
    # The page is still handed back — a failure is not a reason to leak it.
    assert server.deleted_pages == [PAGE_ID]


def test_giving_up_waiting_says_it_may_still_be_running() -> None:
    server = FakeServer(states=["running"])

    with a_client(server) as client, pytest.raises(PipelineExecutionTimedOut, match="still"):
        client.process_page(
            input={},
            pipeline=("p", "1"),
            output={"out.txt"},
            timeout_seconds=0,
        )

    assert server.deleted_pages == [PAGE_ID]


def test_an_unknown_pipeline_is_reported_as_such() -> None:
    server = FakeServer(start_status=404)

    with a_client(server) as client, pytest.raises(PipelineNotAvailable):
        client.process_page(input={}, pipeline=("nothing-like-this", "1.0.0"), output=set())


def test_a_missing_output_file_reports_object_storage_saying_so() -> None:
    # The pipeline completed but produced nothing under that name.
    server = FakeServer()

    with a_client(server) as client, pytest.raises(MusibotApiError, match="404"):
        client.process_page(input={}, pipeline=("p", "1"), output={"transcription.musicxml"})


def test_a_path_that_escapes_its_page_is_refused_before_any_request() -> None:
    server = FakeServer()

    with a_client(server) as client, pytest.raises(MusibotApiError, match=r"\.\."):
        client.upload_files(PAGE_ID, {"../../etc/passwd": b"x"})

    assert server.requests == []


def test_asking_for_nothing_makes_no_request() -> None:
    server = FakeServer()

    with a_client(server) as client:
        assert client.download_files(PAGE_ID, []) == {}
        client.upload_files(PAGE_ID, {})

    assert server.requests == []


def test_a_server_that_cannot_be_reached_says_which_one() -> None:
    def unreachable(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    client = MusibotClient(
        musibot_api_url=API_HOST,
        api_token="secret",
        transport=httpx.MockTransport(unreachable),
    )
    with client, pytest.raises(MusibotApiError, match="Could not reach"):
        client.create_page()


def test_listing_pipelines_includes_implicit_ones() -> None:
    server = FakeServer()

    with a_client(server) as client:
        listing = client.list_pipelines()

    assert [pipeline.name for pipeline in listing.pipelines] == ["hello-model"]
    assert listing.pipelines[0].implicit is True
    assert listing.pipelines[0].signature.output == ["transcription.musicxml"]
    assert listing.warnings == []


def test_the_steps_are_available_on_their_own() -> None:
    """A caller may hold a page open rather than using `process_page`."""
    server = FakeServer(stored={f"{PAGE_ID}/out.txt": b"x"})

    with a_client(server) as client:
        page = client.create_page()
        client.upload_files(page.page_id, {"image.jpg": SCAN})

        first = client.start_execution(page.page_id, "p", "1", ["image.jpg"])
        client.wait_for_execution(page.page_id, first.execution_id)
        second = client.start_execution(page.page_id, "p", "2", ["Staves/1/image.jpg"])
        client.wait_for_execution(page.page_id, second.execution_id)

        assert client.download_files(page.page_id, ["out.txt"]) == {"out.txt": b"x"}
        client.delete_page(page.page_id)

    assert len(server.started) == 2
    # Each execution names its own Files, which is what a caller holding a page
    # open across several of them needs.
    assert [started["input"] for started in server.started] == [
        ["image.jpg"],
        ["Staves/1/image.jpg"],
    ]
    assert server.deleted_pages == [PAGE_ID]
