"""The client, driven against a fake Musibot server over a mocked transport."""

import httpx
import pytest

from musibot.client import (
    MusibotApiError,
    MusibotClient,
    PipelineExecutionFailed,
    PipelineExecutionTimedOut,
    PipelineNotAvailable,
    RetryPolicy,
)
from tests.fake_server import API_HOST, PAGE_ID, FakeServer

SCAN = b"\xff\xd8\xff\xe0 pretend this is a JPEG"
TRANSCRIPTION = b'<?xml version="1.0"?><score-partwise/>'


def a_client(server: FakeServer) -> MusibotClient:
    return MusibotClient(
        musibot_api_url=API_HOST,
        api_token="secret",
        transport=server.transport(),
    )


def test_process_page_round_trip() -> None:
    server = FakeServer(
        objects={f"{PAGE_ID}/transcription.musicxml": TRANSCRIPTION},
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
    server = FakeServer(objects={f"{PAGE_ID}/out.txt": b"x"})

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
    server = FakeServer(objects={f"{PAGE_ID}/out.txt": b"x"})

    with a_client(server) as client:
        client.process_page(input={"image.jpg": SCAN}, pipeline=("p", "1"), output={"out.txt"})

    storage_requests = [r for r in server.requests if r.url.host == "minio.test"]
    assert storage_requests, "the test proved nothing if no transfer happened"
    assert all("Authorization" not in r.headers for r in storage_requests)


def test_it_waits_on_the_stream_rather_than_polling() -> None:
    """The whole reason the result stream exists: one connection, however many
    pages are in flight, and no repeated asking."""
    server = FakeServer(objects={f"{PAGE_ID}/out.txt": b"x"})

    with a_client(server) as client:
        client.process_page(input={}, pipeline=("p", "1"), output={"out.txt"})

    assert server.streams_opened == 1
    # Asked about twice and no more: once by the waiter on its way in, once by
    # the stream as it connected. Both are there because nothing is replayed, so
    # an execution that ended before anyone was watching has to be asked about.
    assert server.polls == 2


def test_an_execution_that_ended_before_anyone_watched_is_still_found() -> None:
    """Nothing is replayed, so the one ask on the way in is what saves a caller
    that arrives late."""
    server = FakeServer(objects={f"{PAGE_ID}/out.txt": b"x"}, settle_immediately=True)

    with a_client(server) as client:
        client.process_page(input={}, pipeline=("p", "1"), output={"out.txt"})

    assert server.deleted_pages == [PAGE_ID]


def test_a_failed_execution_raises_with_the_reason() -> None:
    server = FakeServer(outcome="failed")

    with a_client(server) as client, pytest.raises(PipelineExecutionFailed) as raised:
        client.process_page(input={"image.jpg": SCAN}, pipeline=("p", "1"), output={"out.txt"})

    assert raised.value.error == "No staves found in the image."
    assert raised.value.page_id == PAGE_ID
    # The page is still handed back — a failure is not a reason to leak it.
    assert server.deleted_pages == [PAGE_ID]


def test_giving_up_waiting_says_it_may_still_be_running() -> None:
    server = FakeServer(auto_finish=False)

    with a_client(server) as client, pytest.raises(PipelineExecutionTimedOut, match="still"):
        client.process_page(
            input={},
            pipeline=("p", "1"),
            output={"out.txt"},
            timeout_seconds=0,
            # Giving up waiting is retryable — during an outage it is exactly
            # what a page that was waiting looks like — so the retries are
            # turned off here to test the giving up itself.
            retry=RetryPolicy.none(),
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


def test_listing_files_discovers_what_a_pipeline_produced() -> None:
    """The output *Files* of a page-level run are not knowable in advance —
    how many staves a page has is what the recognition found out — so they are
    discovered and then downloaded by the paths that came back."""
    server = FakeServer(
        objects={
            f"{PAGE_ID}/image.jpg": SCAN,
            f"{PAGE_ID}/Staves/1/transcription.musicxml": TRANSCRIPTION,
        }
    )

    with a_client(server) as client:
        files = client.list_files(PAGE_ID)

        assert [file.path for file in files] == [
            "Staves/1/transcription.musicxml",
            "image.jpg",
        ]
        assert [file.size for file in files] == [len(TRANSCRIPTION), len(SCAN)]

        downloaded = client.download_files(PAGE_ID, [file.path for file in files])
        assert downloaded["Staves/1/transcription.musicxml"] == TRANSCRIPTION


def test_listing_files_of_an_empty_page_finds_nothing() -> None:
    server = FakeServer()

    with a_client(server) as client:
        assert client.list_files(PAGE_ID) == []


def test_the_steps_are_available_on_their_own() -> None:
    """A caller may hold a page open rather than using `process_page`."""
    server = FakeServer(objects={f"{PAGE_ID}/out.txt": b"x"})

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
