"""The batch API: many pages, one *Pipeline*, results as they finish."""

from collections.abc import Iterator
from pathlib import Path

from musibot.client import (
    BatchJob,
    MusibotClient,
    PipelineExecutionFailed,
    PipelineNotAvailable,
    RetryPolicy,
)
from tests.fake_server import API_HOST, FakeServer

SCAN = b"\xff\xd8\xff\xe0 pretend this is a JPEG"
TRANSCRIPTION = b'<?xml version="1.0"?><score-partwise/>'

# Nothing here should wait on a wall clock, so retries are instant. What is
# being tested is which failures are retried, not how long a client sleeps.
PROMPT = RetryPolicy(backoff_seconds=0.0)


def a_client(server: FakeServer) -> MusibotClient:
    return MusibotClient(musibot_api_url=API_HOST, api_token="secret", transport=server.transport())


def jobs(*keys: object) -> Iterator[BatchJob[object]]:
    for key in keys:
        yield BatchJob(key=key, input={"image.jpg": SCAN})


def a_server_producing_transcriptions(pages: int = 3) -> FakeServer:
    """Every page a *Worker* writes a transcription into, whatever its ID."""
    server = FakeServer()
    for page_id in ["7Kf2mP9xLwQa", *[f"page-{index}" for index in range(1, pages + 1)]]:
        server.objects[f"{page_id}/transcription.musicxml"] = TRANSCRIPTION
    return server


def test_a_batch_runs_every_page_and_gives_each_result_its_key() -> None:
    server = a_server_producing_transcriptions()

    with a_client(server) as client:
        results = list(
            client.process_pages(
                jobs("first", "second", "third"),
                pipeline=("hello-model", "1.0.0"),
                output={"transcription.musicxml"},
                concurrency=3,
            )
        )

    assert {result.key for result in results} == {"first", "second", "third"}
    assert all(result.ok for result in results)
    assert all(result.files["transcription.musicxml"] == TRANSCRIPTION for result in results)
    # Every page handed back, none left on the server.
    assert len(server.deleted_pages) == 3


def test_one_stream_serves_every_page_in_flight() -> None:
    """The reason the result stream is scoped to a *User* rather than to a page:
    twenty pages in flight are one connection, not twenty pollers."""
    server = a_server_producing_transcriptions()

    with a_client(server) as client:
        list(
            client.process_pages(
                jobs("a", "b", "c"),
                pipeline=("hello-model", "1.0.0"),
                output={"transcription.musicxml"},
                concurrency=3,
            )
        )

    assert server.streams_opened == 1


def test_a_failed_page_is_a_result_rather_than_an_exception() -> None:
    """One bad scan among a million is not a reason to stop the run."""
    server = FakeServer(outcome="failed")

    with a_client(server) as client:
        results = list(
            client.process_pages(
                jobs("good", "bad"),
                pipeline=("hello-model", "1.0.0"),
                output={"transcription.musicxml"},
                retry=PROMPT,
            )
        )

    assert len(results) == 2
    assert all(result.failed for result in results)
    error = results[0].error
    assert isinstance(error, PipelineExecutionFailed)
    assert error.error == "No staves found in the image."
    # And it says which page it was about, which is the whole point of the key.
    assert {result.key for result in results} == {"good", "bad"}


def test_a_key_may_be_anything_at_all() -> None:
    server = a_server_producing_transcriptions()
    folder = Path("benchmarks/UFAL.OmniOMR/page-7")

    with a_client(server) as client:
        [result] = list(
            client.process_pages(
                jobs(folder),
                pipeline=("hello-model", "1.0.0"),
                output={"transcription.musicxml"},
            )
        )

    assert result.key is folder


def test_output_may_be_chosen_by_a_predicate() -> None:
    """What a page-level recognition produced is not knowable in advance — how
    many staves a page has is its answer — so the page is asked."""
    server = FakeServer()
    server.objects["7Kf2mP9xLwQa/Staves/1/transcription.musicxml"] = TRANSCRIPTION
    server.objects["7Kf2mP9xLwQa/Staves/2/transcription.musicxml"] = TRANSCRIPTION
    server.objects["7Kf2mP9xLwQa/image.jpg"] = SCAN

    with a_client(server) as client:
        [result] = list(
            client.process_pages(
                jobs("page"),
                pipeline=("hello-model", "1.0.0"),
                output=lambda file: file.path.endswith(".musicxml"),
            )
        )

    assert sorted(result.files) == [
        "Staves/1/transcription.musicxml",
        "Staves/2/transcription.musicxml",
    ]


def test_jobs_are_pulled_only_as_workers_free_up() -> None:
    """A million-page run must not hold a million scans: the generator that
    fetches each one is asked for a page only when there is a worker for it."""
    pulled: list[int] = []

    def counted() -> Iterator[BatchJob[int]]:
        for index in range(5):
            pulled.append(index)
            yield BatchJob(key=index, input={"image.jpg": SCAN})

    server = a_server_producing_transcriptions(pages=5)

    with a_client(server) as client:
        stream = client.process_pages(
            counted(),
            pipeline=("hello-model", "1.0.0"),
            output={"transcription.musicxml"},
            concurrency=1,
        )
        next(stream)
        # One page done, so at most the next one has been taken in hand.
        assert len(pulled) <= 2
        stream.close()


def test_stopping_early_leaves_no_page_behind() -> None:
    server = a_server_producing_transcriptions(pages=5)

    with a_client(server) as client:
        for _ in client.process_pages(
            jobs(*range(5)),
            pipeline=("hello-model", "1.0.0"),
            output={"transcription.musicxml"},
            concurrency=1,
        ):
            break  # a `break`, a KeyboardInterrupt — the run stops here

    # Whatever was created was given back, including the page in hand when the
    # caller walked away.
    assert len(server.deleted_pages) == len(server.executions)


# --- retries -------------------------------------------------------------------


def test_a_service_that_is_restarting_is_waited_out() -> None:
    """The overnight case: something in the way restarts, and the morning finds
    the run finished rather than 98% finished."""
    server = a_server_producing_transcriptions()
    server.failures = {"/api/musicorpus-pages": 2}

    with a_client(server) as client:
        [result] = list(
            client.process_pages(
                jobs("page"),
                pipeline=("hello-model", "1.0.0"),
                output={"transcription.musicxml"},
                retry=PROMPT,
            )
        )

    assert result.ok
    assert result.attempts == 3


def test_a_connection_that_never_answered_is_waited_out_too() -> None:
    """The laptop-loses-its-wifi case, which arrives with no status code at
    all."""
    server = a_server_producing_transcriptions()
    server.failures = {"/api/musicorpus-pages": 1}
    server.failure_status = 0  # no answer, as a refused connection gives

    with a_client(server) as client:
        [result] = list(
            client.process_pages(
                jobs("page"),
                pipeline=("hello-model", "1.0.0"),
                output={"transcription.musicxml"},
                retry=PROMPT,
            )
        )

    assert result.ok
    assert result.attempts == 2


def test_a_pipeline_that_ran_and_failed_is_not_retried() -> None:
    """The *Model* answered. Asking it the same question again is not a fix."""
    server = FakeServer(outcome="failed")

    with a_client(server) as client:
        [result] = list(
            client.process_pages(
                jobs("page"),
                pipeline=("hello-model", "1.0.0"),
                output={"transcription.musicxml"},
                retry=PROMPT,
            )
        )

    assert result.failed
    assert result.attempts == 1


def test_a_request_the_server_refused_is_not_retried() -> None:
    """A pipeline nobody provides is a typo, not weather."""
    server = FakeServer(start_status=404)

    with a_client(server) as client:
        [result] = list(
            client.process_pages(
                jobs("page"),
                pipeline=("nothing-like-this", "1.0.0"),
                output=set(),
                retry=PROMPT,
            )
        )

    assert isinstance(result.error, PipelineNotAvailable)
    assert result.attempts == 1


def test_a_run_of_bad_luck_gives_up_and_says_so() -> None:
    server = a_server_producing_transcriptions()
    server.failures = {"/api/musicorpus-pages": 10}

    with a_client(server) as client:
        [result] = list(
            client.process_pages(
                jobs("page"),
                pipeline=("hello-model", "1.0.0"),
                output={"transcription.musicxml"},
                retry=RetryPolicy(attempts=3, backoff_seconds=0.0),
            )
        )

    assert result.failed
    assert result.attempts == 3
    assert "503" in str(result.error)


def test_retries_may_be_switched_off() -> None:
    server = a_server_producing_transcriptions()
    server.failures = {"/api/musicorpus-pages": 1}

    with a_client(server) as client:
        [result] = list(
            client.process_pages(
                jobs("page"),
                pipeline=("hello-model", "1.0.0"),
                output={"transcription.musicxml"},
                retry=RetryPolicy.none(),
            )
        )

    assert result.failed
    assert result.attempts == 1


# --- watching -------------------------------------------------------------------


def test_watching_results_yields_endings_as_they_happen() -> None:
    server = FakeServer()

    with a_client(server) as client:
        page = client.create_page()
        client.start_execution(page.page_id, "hello-model", "1.0.0", ["image.jpg"])

        for ended in client.watch_execution_results():
            assert ended.page_id == page.page_id
            assert ended.execution.state == "completed"
            break
