"""The one connection that says which executions have ended.

A *Pipeline Execution* used to be waited on by asking every second whether it
had finished. The `api` service now streams every ending of this token's
identity from a single endpoint, so one connection serves however many pages a
client has in flight — which is the whole reason a batch can hold twenty pages
open without twenty pollers.

The stream promises little, and this module is mostly the handling of that.
Nothing is replayed, so an execution that ended before a waiter existed, or
while the connection was down, is never announced — and every connection
therefore reconciles by asking about the executions currently being waited on.
A stream that says nothing for `STALL_SECONDS` is presumed dead and reopened,
because a connection killed by something in the middle is otherwise
indistinguishable from a page that is simply taking its time.
"""

import logging
import threading
from collections.abc import Callable, Iterator

import httpx

from musibot.client.errors import PipelineExecutionTimedOut
from musibot.client.models import ExecutionResult, PipelineExecution

logger = logging.getLogger(__name__)

RESULTS_PATH = "/pipeline-execution-results"

STALL_SECONDS = 45.0
"""How long a stream may say nothing before it is presumed dead.

The service sends a keepalive comment every 15 seconds, so this is three missed
ones. It is not "how long an execution may take": a silent stream is silent
whatever its executions are doing.
"""

RECONNECT_SECONDS = 2.0

CLOSE_SECONDS = 0.25
"""How long a closing client waits for the stream thread to notice.

Barely at all, deliberately: the thread is blocked reading a socket the client
is about to close underneath it, and that is what actually ends it. Waiting for
it to answer would mean sitting out the server's keepalive interval every time
a script finished its work."""

_TICK_SECONDS = 0.2
"""How often a blocked waiter looks up to see whether it is being shut down.

An in-process event, so this costs nothing and is what makes a Ctrl+C during a
batch land promptly rather than after a whole execution timeout.
"""


class _Waiter:
    def __init__(self) -> None:
        self.settled: PipelineExecution | None = None
        self.arrived = threading.Event()


class ResultWatcher:
    """Watches this *User's* executions and wakes whoever is waiting on one.

    One per client, started the first time something waits and stopped when the
    client is closed. `fetch` is how it asks about a single execution, which it
    does on connect and reconnect rather than on a timer.
    """

    def __init__(
        self,
        http: httpx.Client,
        base_url: str,
        headers: dict[str, str],
        fetch: Callable[[str, int], PipelineExecution],
    ):
        self._http = http
        self._url = base_url + RESULTS_PATH
        self._headers = headers
        self._fetch = fetch

        self._waiters: dict[tuple[str, int], _Waiter] = {}
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()

    # --- waiting -------------------------------------------------------------

    def wait_for(
        self,
        page_id: str,
        execution_id: int,
        *,
        timeout_seconds: float,
        stop: threading.Event | None = None,
    ) -> PipelineExecution:
        """Block until this execution ends, and return it however it ended.

        Raises :class:`PipelineExecutionTimedOut` if it has not ended within
        `timeout_seconds` — which says this client stopped watching, not that
        the server gave up. `stop`, when given, abandons the wait early and
        raises the same error; a batch passes its shutdown signal here so that
        an interrupted run does not sit out a full execution timeout.
        """
        key = (page_id, execution_id)
        waiter = _Waiter()
        with self._lock:
            self._waiters[key] = waiter
            self._ensure_running()

        try:
            # Registered first, then asked: nothing is replayed, so an execution
            # that ended a moment ago would otherwise be waited on for ever.
            # Doing it in this order means a result arriving in between is
            # caught by the waiter rather than falling between the two.
            current = self._fetch(page_id, execution_id)
            if not current.is_running:
                return current

            waited = 0.0
            while not waiter.arrived.wait(_TICK_SECONDS):
                waited += _TICK_SECONDS
                if stop is not None and stop.is_set():
                    raise PipelineExecutionTimedOut(
                        f"Stopped waiting for execution {execution_id} of page {page_id}",
                        page_id=page_id,
                        execution_id=execution_id,
                    )
                if waited >= timeout_seconds:
                    raise PipelineExecutionTimedOut(
                        f"Gave up waiting for execution {execution_id} of page {page_id} "
                        f"after {timeout_seconds:.0f}s; it may still be running",
                        page_id=page_id,
                        execution_id=execution_id,
                    )

            settled = waiter.settled
            assert settled is not None  # set before the event, by _settle
            return settled
        finally:
            with self._lock:
                self._waiters.pop(key, None)

    def close(self) -> None:
        """Stop watching. Called when the client is closed.

        The thread is given a moment and then left to it — see
        `CLOSE_SECONDS`. It is a daemon, so an interpreter shutdown does not
        wait for it either.
        """
        self._stop.set()
        thread = self._thread
        if thread is not None:
            thread.join(timeout=CLOSE_SECONDS)
        self._thread = None

    # --- the stream ----------------------------------------------------------

    def _ensure_running(self) -> None:
        """Start the stream thread, once. Called under the lock."""
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop.clear()
        # A daemon thread: it holds no resource an interpreter shutdown would
        # want back, and a client that is never closed must not keep a process
        # alive because of it.
        self._thread = threading.Thread(target=self._run, name="musibot-results", daemon=True)
        self._thread.start()

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                self._consume()
            except Exception as error:
                if self._stop.is_set():
                    return
                # Everything reconnects: a service restarting, a proxy closing
                # an idle connection, a laptop losing its network. The waiters
                # are reconciled on the way back in, so a reconnection costs
                # latency and nothing else.
                logger.debug("The result stream dropped (%s); reconnecting", error, exc_info=True)
            self._stop.wait(RECONNECT_SECONDS)

    def _consume(self) -> None:
        timeout = httpx.Timeout(connect=10.0, read=STALL_SECONDS, write=10.0, pool=10.0)
        with self._http.stream(
            "POST", self._url, headers=self._headers, timeout=timeout
        ) as response:
            if response.status_code != 200:
                response.read()
                raise httpx.HTTPError(f"The result stream answered {response.status_code}")

            # Connected. Whatever ended while nothing was watching is not coming
            # down this stream, so it is asked for instead.
            self._reconcile()

            for event in _iter_events(response):
                if self._stop.is_set():
                    return
                self._dispatch(event)

    def _reconcile(self) -> None:
        for (page_id, execution_id), _ in self._waiting():
            try:
                execution = self._fetch(page_id, execution_id)
            except Exception:
                # Asking failed too, which means the trouble is not over. The
                # next reconnection asks again, and the caller's own timeout is
                # what eventually decides.
                logger.debug("Could not ask about %s/%d", page_id, execution_id, exc_info=True)
                continue
            if not execution.is_running:
                self._settle(page_id, execution_id, execution)

    def _dispatch(self, payload: str) -> None:
        try:
            result = ExecutionResult.model_validate_json(payload)
        except ValueError:
            logger.debug("Ignoring an unreadable event on the result stream")
            return
        self._settle(result.page_id, result.execution.execution_id, result.execution)

    def _settle(self, page_id: str, execution_id: int, execution: PipelineExecution) -> None:
        with self._lock:
            waiter = self._waiters.get((page_id, execution_id))
        if waiter is None:
            return  # another script's page, or one nobody is waiting on any more
        waiter.settled = execution
        waiter.arrived.set()

    def _waiting(self) -> list[tuple[tuple[str, int], _Waiter]]:
        with self._lock:
            return list(self._waiters.items())


def _iter_events(response: httpx.Response) -> Iterator[str]:
    """The `data` of each Server-Sent Event, as it arrives.

    Comment frames (`: ping`) keep an idle stream open and carry nothing, so
    they are dropped here rather than being every caller's problem.
    """
    data: list[str] = []
    for line in response.iter_lines():
        line = line.rstrip("\r")

        if line == "":
            if data:
                yield "\n".join(data)
                data = []
            continue

        if line.startswith(":"):
            continue

        if line.startswith("data:"):
            data.append(line[len("data:") :].lstrip())


def parse_events(response: httpx.Response) -> Iterator[ExecutionResult]:
    """Every ending the stream announces, parsed. What `watch_execution_results`
    hands a caller."""
    for payload in _iter_events(response):
        try:
            yield ExecutionResult.model_validate_json(payload)
        except ValueError:
            logger.debug("Ignoring an unreadable event on the result stream")
