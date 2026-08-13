"""Running many pages through one *Pipeline*.

The shape a library-scale workload wants: hand it an iterable of pages, get
results back as they finish, and keep going when one of them fails. A whole
collection is millions of pages and a single bad scan among them is not a
reason to stop.

Three decisions are worth knowing before reading the code.

**Failure is a result, not an exception.** A page that fails comes back with its
error attached, carrying the key you gave it, so recording it and moving on is
the caller's ordinary loop rather than a `try` around everything. Exceptions are
kept for what ends the whole run — a bad token, a server that is not there.

**Infrastructure failures are retried; a *Model* saying no is not.** A proxy
restarted overnight, a laptop that lost its wifi, a `429` from the public tier:
those are waited out, with a backoff and a visible warning, because a run that
came back 98% complete in the morning is worse than one that took an hour
longer. "No staves found in the image" is an answer, and answers are not
retried.

**Concurrency is threads.** The work is socket waiting, so the GIL is released
throughout, and the useful number of pages in flight is bounded by the *Worker*
fleet — a handful — rather than by anything here. The waiting itself costs no
requests at all: every worker waits on one shared result stream (see
`results.py`), which is what this whole design is for.
"""

import logging
import queue
import threading
import time
from collections.abc import Callable, Generator, Iterable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Generic, TypeVar

from musibot.client.errors import (
    MusibotApiError,
    PipelineExecutionFailed,
    PipelineExecutionTimedOut,
)
from musibot.client.models import PageFile, PipelineExecution

if TYPE_CHECKING:
    from musibot.client.client import MusibotClient

logger = logging.getLogger(__name__)

T = TypeVar("T")

OutputSelector = Iterable[str] | Callable[[PageFile], bool]
"""Which *Files* to bring back from a finished page.

Either the paths outright — cheap, and what a caller who knows the *Pipeline's*
output knows — or a predicate over the page's listing, for the outputs nobody
can name in advance because the recognition decides how many there are.
"""

RETRYABLE_STATUS_CODES = frozenset({429, 500, 502, 503, 504})
"""Server answers worth waiting out. Everything else in the 4xx range is a
statement about the request — a bad token, a page that is gone, an input list
that does not fit — and asking again changes nothing."""


@dataclass
class RetryPolicy:
    """How hard to try when the trouble is not the page's fault.

    The defaults ride out a quarter of an hour of network or service trouble,
    which covers the restart-during-the-night case. An overnight run over a
    whole collection can afford to raise `give_up_after_seconds` a long way:
    the alternative is a second pass in the morning.
    """

    attempts: int = 6
    """The first try plus five more."""

    backoff_seconds: float = 1.0
    """The first wait. Doubles with each attempt."""

    max_backoff_seconds: float = 60.0
    """A ceiling on the doubling, so a long outage is retried steadily rather
    than at increasingly useless intervals."""

    give_up_after_seconds: float = 900.0
    """The whole budget for one page, across every attempt."""

    @classmethod
    def none(cls) -> "RetryPolicy":
        """Try once and report whatever happens."""
        return cls(attempts=1)


@dataclass
class BatchJob(Generic[T]):
    """One page's worth of work."""

    input: dict[str, bytes]
    """The *Files* to upload, keyed by their path within the page. The
    execution runs over exactly these."""

    key: T = None  # type: ignore[assignment]
    """Yours, echoed back untouched on the result: a database UUID, a folder, a
    row object. Musibot never looks at it."""

    parameters: dict[str, Any] | None = None
    """Overrides the batch's parameters, for the page that needs something
    different."""


@dataclass
class BatchResult(Generic[T]):
    """What became of one job."""

    key: T
    page_id: str
    files: dict[str, bytes] = field(default_factory=dict)
    execution: PipelineExecution | None = None
    error: Exception | None = None
    attempts: int = 1
    """How many tries it took. Worth reading even on success: a run that
    quietly took three attempts a page is a run with something wrong under it."""

    seconds: float = 0.0
    """The whole round trip, waiting between retries included."""

    @property
    def ok(self) -> bool:
        return self.error is None

    @property
    def failed(self) -> bool:
        return self.error is not None


# --- one page ------------------------------------------------------------------


def process_one(
    client: "MusibotClient",
    job: BatchJob[T],
    pipeline: tuple[str, str],
    output: OutputSelector,
    *,
    parameters: dict[str, Any] | None = None,
    timeout_seconds: float,
    retry: RetryPolicy,
    stop: threading.Event | None = None,
) -> BatchResult[T]:
    """Run one page, retrying what is worth retrying, and report the outcome.

    Never raises for anything about this page: the outcome is the return value,
    which is what lets a batch loop over a million of them.
    """
    started = time.monotonic()
    attempt = 0
    outcome = _Outcome(page_id="")

    while True:
        attempt += 1
        outcome = _attempt(client, job, pipeline, output, parameters, timeout_seconds, stop)

        if outcome.error is None:
            break

        elapsed = time.monotonic() - started
        delay = _delay_before_retry(attempt, outcome.error, retry)

        if (
            not _is_retryable(outcome.error)
            or attempt >= retry.attempts
            or elapsed + delay >= retry.give_up_after_seconds
            or (stop is not None and stop.is_set())
        ):
            break

        # Said out loud: a page that needed three goes is a symptom, and a run
        # that hid it looks like a healthy run that was merely slow.
        logger.warning(
            "Page %s failed (%s); attempt %d of %d, retrying in %.0fs",
            job.key if job.key is not None else outcome.page_id,
            outcome.error,
            attempt,
            retry.attempts,
            delay,
        )
        if stop is not None:
            if stop.wait(delay):
                break
        else:
            time.sleep(delay)

    return BatchResult(
        key=job.key,
        page_id=outcome.page_id,
        files=outcome.files,
        execution=outcome.execution,
        error=outcome.error,
        attempts=attempt,
        seconds=time.monotonic() - started,
    )


@dataclass
class _Outcome:
    """One attempt at one page. Carries its page ID even when it failed, since
    that is what a caller needs to find the wreckage in a server log."""

    page_id: str
    files: dict[str, bytes] = field(default_factory=dict)
    execution: PipelineExecution | None = None
    error: Exception | None = None


def _attempt(
    client: "MusibotClient",
    job: BatchJob[T],
    pipeline: tuple[str, str],
    output: OutputSelector,
    parameters: dict[str, Any] | None,
    timeout_seconds: float,
    stop: threading.Event | None,
) -> _Outcome:
    """One whole round trip: a page created, used and given back.

    A retry starts here again rather than resuming where it broke. Recognition
    is a second or two and a scan is a megabyte, while a page abandoned mid-way
    through an outage may have been evicted or had its execution time out — so
    beginning again is both the simple thing and the correct one.
    """
    name, version = pipeline
    page_id = ""
    try:
        page_id = client.create_page().page_id
        client.upload_files(page_id, job.input)

        execution = client.start_execution(
            page_id,
            name,
            version,
            list(job.input),
            {**(parameters or {}), **(job.parameters or {})},
        )
        settled = client.wait_for_execution(
            page_id, execution.execution_id, timeout_seconds=timeout_seconds, stop=stop
        )

        if not settled.is_completed:
            return _Outcome(
                page_id=page_id,
                execution=settled,
                error=PipelineExecutionFailed(
                    f"Pipeline {name!r} version {version!r} failed: "
                    f"{settled.error or 'no reason given'}",
                    page_id=page_id,
                    execution_id=settled.execution_id,
                    error=settled.error,
                ),
            )

        return _Outcome(
            page_id=page_id,
            files=_download(client, page_id, output),
            execution=settled,
        )

    except Exception as error:  # noqa: BLE001 — every failure becomes a result
        # Deliberately everything. Whatever went wrong with this page is the
        # caller's to read on the result and mine to decide whether to retry;
        # letting it out here would end a run of a million pages over one of
        # them.
        return _Outcome(page_id=page_id, error=error)

    finally:
        if page_id:
            # The page is this client's and nothing else will want it; a server
            # left holding one only evicts it later under disk pressure. Deleted
            # on the way out of a failed attempt too, which is also what stops a
            # retry from leaving its predecessor's execution running.
            try:
                client.delete_page(page_id)
            except Exception:
                logger.warning("Could not delete page %s", page_id, exc_info=True)


def _download(client: "MusibotClient", page_id: str, output: OutputSelector) -> dict[str, bytes]:
    if callable(output):
        # What the recognition produced is not knowable in advance — how many
        # staves a page has is its answer — so the page is asked what it holds
        # and the predicate decides.
        paths = [file.path for file in client.list_files(page_id) if output(file)]
    else:
        paths = list(output)
    return client.download_files(page_id, paths)


def _is_retryable(error: Exception) -> bool:
    """Whether trying again could plausibly do better.

    A *Pipeline* that failed is not retried: the *Model* answered, and running
    it a second time over the same bytes asks the same question. A client-side
    timeout is, because during an outage that is exactly what a page that was
    waiting looks like.
    """
    if isinstance(error, PipelineExecutionFailed):
        return False
    if isinstance(error, PipelineExecutionTimedOut):
        return True
    if isinstance(error, MusibotApiError):
        # No status code means the request never got an answer at all: a refused
        # connection, a name that would not resolve, a read that timed out.
        return error.status_code is None or error.status_code in RETRYABLE_STATUS_CODES
    return False


def _delay_before_retry(attempt: int, error: Exception, retry: RetryPolicy) -> float:
    after: object = getattr(error, "retry_after_seconds", None)
    if isinstance(after, int | float) and after > 0:
        # The server knows how long its own caps last, which beats any backoff
        # invented here.
        return min(float(after), retry.max_backoff_seconds)
    doubling: float = retry.backoff_seconds * (2 ** (attempt - 1))
    return min(doubling, retry.max_backoff_seconds)


# --- many pages ----------------------------------------------------------------


class _JobSource(Generic[T]):
    """The caller's jobs, handed out one at a time.

    Pulled lazily and under a lock, so a generator that fetches a scan from an
    image server is both safe to consume from several workers and never asked
    for more pages than are about to be worked on. A million-page run therefore
    never holds a million scans.
    """

    def __init__(self, jobs: Iterable[BatchJob[T]]):
        self._jobs = iter(jobs)
        self._lock = threading.Lock()
        self._exhausted = False

    def next(self) -> BatchJob[T] | None:
        with self._lock:
            if self._exhausted:
                return None
            try:
                return next(self._jobs)
            except StopIteration:
                self._exhausted = True
                return None


def process_pages(
    client: "MusibotClient",
    jobs: Iterable[BatchJob[T]],
    pipeline: tuple[str, str],
    output: OutputSelector,
    *,
    concurrency: int = 4,
    parameters: dict[str, Any] | None = None,
    timeout_seconds: float,
    retry: RetryPolicy | None = None,
) -> Generator[BatchResult[T], None, None]:
    """Run many pages through one *Pipeline*, yielding results as they finish."""
    policy = retry if retry is not None else RetryPolicy()
    workers = max(1, concurrency)

    stop = threading.Event()
    finished: queue.Queue[BatchResult[T] | None] = queue.Queue()
    source: _JobSource[T] = _JobSource(jobs)

    def work() -> None:
        try:
            while not stop.is_set():
                job = source.next()
                if job is None:
                    return
                finished.put(
                    process_one(
                        client,
                        job,
                        pipeline,
                        output,
                        parameters=parameters,
                        timeout_seconds=timeout_seconds,
                        retry=policy,
                        stop=stop,
                    )
                )
        finally:
            # One sentinel per worker, so the loop below knows when the last of
            # them has gone rather than guessing at it.
            finished.put(None)

    threads = [
        threading.Thread(target=work, name=f"musibot-batch-{index}", daemon=True)
        for index in range(workers)
    ]
    for thread in threads:
        thread.start()

    try:
        running = len(threads)
        while running > 0:
            item = finished.get()
            if item is None:
                running -= 1
                continue
            yield item
    finally:
        # A caller that stops reading — a `break`, a `KeyboardInterrupt` — stops
        # the run. Workers notice between steps and while waiting, so a page in
        # flight is abandoned and deleted rather than left on the server.
        stop.set()
        for thread in threads:
            thread.join(timeout=10.0)
        lingering = [thread.name for thread in threads if thread.is_alive()]
        if lingering:
            logger.warning(
                "Gave up waiting for %s; their pages will expire on the server",
                ", ".join(lingering),
            )
