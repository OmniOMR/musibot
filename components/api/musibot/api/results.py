"""Execution results on their way to whoever asked for the work.

The third of the service's streams, and the only one scoped to a *User* rather
than to a page. That is because of who wants it: a client holding twenty pages
in flight wants one connection telling it which have finished, not twenty; and
the Web UI's session screen wants the same thing for the pages in this browser.
A page-scoped stream would serve neither, and a page screen filters this one by
page ID at no cost.

Nothing is published here from RabbitMQ. This service settles every *Pipeline
Execution* itself — from an *Orchestrator's* result, from a *Model's* result
when it is running an *ImplicitPipeline*, or from its own timeout — so a result
stream is a fan-out of something it already knows.

There is no session in Musibot: a *Library* token resolves to an identity, and
this stream carries every page of that identity, including pages another holder
of the same token created. A client watches for the page IDs it created and
ignores the rest — which it can, because it is already obliged to track them.
See `docs/http-api.md`.
"""

import asyncio
import logging
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, replace

from musibot.api.domain import PipelineExecution
from musibot.api.streams import Watchers

logger = logging.getLogger(__name__)

SUBSCRIBER_QUEUE_SIZE = 1000
"""How far behind a watcher may fall before it is disconnected.

Reaching this means a client that has stopped reading its socket, not a busy
one: a result is a few hundred bytes and an execution takes seconds. It is
bounded because an unbounded queue behind a stalled reader is a slow leak.
"""


@dataclass(frozen=True)
class ExecutionResult:
    """One *Pipeline Execution* that has ended, and the page it belongs to."""

    page_id: str
    # A snapshot taken when the execution settled. The domain object it was
    # copied from is not shared, so a result waiting in a queue cannot describe
    # a state the execution reached afterwards.
    execution: PipelineExecution


class ResultSubscription:
    """One client watching one identity's executions.

    A queue rather than the file-change stream's coalescing, because two
    results are two facts: which pages have finished is not a question with one
    answer, and a client waiting on a page it never hears about waits forever.

    A watcher that overruns the queue is **disconnected** rather than quietly
    missing one. Recovering from a dropped connection is something a client of
    this stream must be able to do anyway — nothing is replayed, so it
    reconciles by asking about the pages it has not heard about — and silently
    losing a result would send it down a path it has no way to notice.
    """

    def __init__(self, identity: str, queue_size: int = SUBSCRIBER_QUEUE_SIZE):
        self.identity = identity
        self.overrun = False
        self._queue: asyncio.Queue[ExecutionResult] = asyncio.Queue(maxsize=queue_size)

    def offer(self, result: ExecutionResult) -> None:
        try:
            self._queue.put_nowait(result)
        except asyncio.QueueFull:
            self.overrun = True

    async def next_result(self, timeout: float) -> ExecutionResult | None:
        """The next result, or None if `timeout` passed with nothing to say —
        which the caller answers with a keepalive."""
        try:
            return await asyncio.wait_for(self._queue.get(), timeout=timeout)
        except TimeoutError:
            return None


class ResultHub:
    """Every ended execution on its way to a client, and who is waiting."""

    def __init__(self) -> None:
        self._watchers: Watchers[ResultSubscription] = Watchers(ResultSubscription)

    @contextmanager
    def subscribe(self, identity: str) -> Iterator[ResultSubscription]:
        """Watch one identity's executions for as long as the block runs."""
        with self._watchers.watch(identity) as subscription:
            yield subscription

    def is_watched(self, identity: str) -> bool:
        return self._watchers.any(identity)

    def publish(self, owner: str, page_id: str, execution: PipelineExecution) -> None:
        """Offer one ended execution to whoever is watching that identity.

        Synchronous and never awaiting: it is called from the middle of settling
        an execution, and a client that has stopped reading its socket must not
        be able to hold that up.
        """
        watchers = self._watchers.of(owner)
        if not watchers:
            return  # nobody is watching this identity, so it goes nowhere

        result = ExecutionResult(page_id=page_id, execution=replace(execution))
        for subscription in watchers:
            subscription.offer(result)
