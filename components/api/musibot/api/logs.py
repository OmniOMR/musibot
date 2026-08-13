"""The log stream: what a *Model* or a *Pipeline* printed, on its way to a *User*.

Everything the fleet logs arrives here on the `musibot.logs` exchange, and this
service is where it stops unless somebody is watching. A *User* watches a
*MusicorpusPage* — not one *Pipeline Execution* — because a page may be read
several times and whoever is debugging a reading wants the whole story in the
order it happened; so a line is routed by the page its execution belongs to.

Nothing is stored. A line arriving while nobody watches that page is dropped and
is not recoverable afterwards: this is a *User* watching a page being read, not
an audit trail, and keeping a buffer per page would make the one service that
holds all the state hold rather more of it.

The service adds lines of its own — an execution started, finished, timed out.
It is the only participant that knows those moments, and without them a log of a
silent *Model* would be an empty panel while something was plainly happening.
"""

import asyncio
import logging
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal

from musibot.core.logs import LogLevel, parse_log_message
from pydantic import ValidationError

from musibot.api.domain import MusicorpusPageRepository, PageNotFound
from musibot.api.streams import Watchers

logger = logging.getLogger(__name__)

SourceKind = Literal["worker", "orchestrator", "api"]
"""Who produced a line. `api` is this service speaking about an execution's
lifecycle; the other two come off the exchange."""

API_SOURCE_NAME = "api"

SUBSCRIBER_QUEUE_SIZE = 1000
"""How many lines may wait for one slow watcher before lines start being lost.

A page's whole reading is a few dozen lines, so reaching this means a client
that has stopped reading its socket rather than a chatty *Model*. It is bounded
because an unbounded queue behind a stalled reader is a slow memory leak.
"""


@dataclass(frozen=True)
class LogLine:
    """One line as a watcher sees it.

    `seconds` is time since its *Pipeline Execution* started, not a wall clock:
    what a reader is judging is how long a step took, not what time of day it
    was. It is measured against this service's clock — the one clock every line
    passes through — rather than the timestamp the source stamped on it, since
    a *Worker* on another machine may disagree by seconds.
    """

    execution_id: int
    seconds: float
    kind: SourceKind
    source: str
    level: LogLevel
    message: str


class LogSubscription:
    """One watcher of one page.

    A bounded queue, and a count of what did not fit. Overflow drops the newest
    line rather than blocking the consumer that offered it: a stalled watcher
    must not be able to slow down the RabbitMQ consumer, and through it every
    other watcher.
    """

    def __init__(self, page_id: str, queue_size: int = SUBSCRIBER_QUEUE_SIZE):
        self.page_id = page_id
        self._queue: asyncio.Queue[LogLine] = asyncio.Queue(maxsize=queue_size)
        self._dropped = 0

    def offer(self, line: LogLine) -> None:
        try:
            self._queue.put_nowait(line)
        except asyncio.QueueFull:
            self._dropped += 1

    async def next_line(self, timeout: float) -> LogLine | None:
        """The next line, or None if `timeout` passed with nothing to say.

        The caller uses that None to send a keepalive, which is what keeps a
        proxy from closing an idle stream.
        """
        if self._dropped > 0:
            # Said rather than swallowed: a log with a silent hole in it is
            # worse than one that admits to the hole.
            dropped, self._dropped = self._dropped, 0
            return LogLine(
                execution_id=0,
                seconds=0.0,
                kind="api",
                source=API_SOURCE_NAME,
                level="warning",
                message=f"{dropped} line(s) dropped — this client could not keep up",
            )
        try:
            return await asyncio.wait_for(self._queue.get(), timeout=timeout)
        except TimeoutError:
            return None


class LogHub:
    """Every log line on its way to a *User*, and the watchers waiting for one."""

    def __init__(self, repository: MusicorpusPageRepository):
        self._repository = repository
        self._watchers: Watchers[LogSubscription] = Watchers(LogSubscription)

    # --- watching ------------------------------------------------------------

    @contextmanager
    def subscribe(self, page_id: str) -> Iterator[LogSubscription]:
        """Watch one page for as long as the block runs."""
        with self._watchers.watch(page_id) as subscription:
            yield subscription

    def is_watched(self, page_id: str) -> bool:
        return self._watchers.any(page_id)

    # --- what arrives --------------------------------------------------------

    async def handle_message(self, body: bytes) -> None:
        """Take one message off the `musibot.logs` exchange.

        Every *Worker* and *Orchestrator* in the fleet publishes here, whether
        or not anyone is listening, so the common case is a line about a page
        nobody is watching — which costs a parse and a dictionary lookup.
        """
        try:
            message = parse_log_message(body)
        except ValidationError:
            logger.warning("Dropping an unintelligible message on the log exchange")
            return

        reference = message.pipeline_execution
        self.publish(
            reference.page_id,
            reference.execution_id,
            message.message,
            level=message.level,
            kind=message.source.kind,
            source=message.source.name,
        )

    def publish(
        self,
        page_id: str,
        execution_id: int,
        message: str,
        *,
        level: LogLevel = "info",
        kind: SourceKind = "api",
        source: str = API_SOURCE_NAME,
    ) -> None:
        """Offer one line to whoever is watching that page.

        Synchronous, and never awaits: it is called from the middle of settling
        an execution as readily as from the RabbitMQ consumer, and a log line
        must not be a reason for either of those to yield.
        """
        watchers = self._watchers.of(page_id)
        if not watchers:
            return  # nobody is watching this page, so the line goes nowhere

        seconds = self._seconds_into(page_id, execution_id)
        if seconds is None:
            # An execution this service does not know about — a *Worker* left
            # running after its page was deleted, say. There is nothing to
            # attribute the line to and nobody it would mean anything to.
            return

        line = LogLine(
            execution_id=execution_id,
            seconds=seconds,
            kind=kind,
            source=source,
            level=level,
            message=message,
        )
        for subscription in watchers:
            subscription.offer(line)

    def _seconds_into(self, page_id: str, execution_id: int) -> float | None:
        """How far into its *Pipeline Execution* a line arriving now is."""
        try:
            page = self._repository.get(page_id)
        except PageNotFound:
            return None

        execution = page.executions.get(execution_id)
        if execution is None:
            return None
        return (datetime.now(UTC) - execution.started_at).total_seconds()
