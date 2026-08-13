"""File changes: what an execution wrote, on its way to a client watching.

The counterpart of `logs.py`, and deliberately not the same stream. A log line
is text for a human and there are a great many of them — most of a deep-learning
model's output is somebody else's warnings — while a notice here is a handful of
paths for a program to act on. Merging them would make every client that wants
to know about a *File* read and discard the whole log.

Nothing here is stored, and nothing depends on a notice arriving: object storage
is the truth about what a page holds, and a client that misses one is a poll
away from finding out. What this buys is latency — a *File* shown as it appears
rather than at the next poll.
"""

import asyncio
import logging
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass

from musibot.core.file_changes import parse_file_change_message
from pydantic import ValidationError

from musibot.api.streams import Watchers

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class FileChange:
    """*Files* one *Pipeline Execution* has written."""

    execution_id: int
    paths: list[str]


class FileChangeSubscription:
    """One watcher of one page's files.

    Notices **coalesce** rather than queue, which is the whole difference from
    the log's subscription. A watcher that has not read for a while does not
    want six notices about the same six paths; it wants to know which paths
    changed since it last looked, and that set is bounded by the page itself —
    so there is no queue to overflow and nothing to drop. A log line, being one
    moment of text, has neither property.
    """

    def __init__(self, page_id: str):
        self.page_id = page_id
        # Kept per execution rather than as one set, so that a notice still says
        # who wrote what — which is knowable at this moment and never again,
        # since a later execution may overwrite any of it.
        self._pending: dict[int, list[str]] = {}
        self._arrived = asyncio.Event()

    def offer(self, execution_id: int, paths: list[str]) -> None:
        known = self._pending.setdefault(execution_id, [])
        known.extend(path for path in paths if path not in known)
        self._arrived.set()

    async def next_changes(self, timeout: float) -> list[FileChange] | None:
        """Everything that changed since the last call, or None if `timeout`
        passed with nothing to say — which the caller answers with a keepalive."""
        try:
            await asyncio.wait_for(self._arrived.wait(), timeout)
        except TimeoutError:
            return None

        self._arrived.clear()
        pending, self._pending = self._pending, {}
        return [
            FileChange(execution_id=execution_id, paths=paths)
            for execution_id, paths in pending.items()
        ]


class FileChangeHub:
    """Every file-change notice on its way to a client, and who is waiting.

    Unlike the log hub this needs no repository: a notice is forwarded as it
    stands, with nothing to work out from the execution it names.
    """

    def __init__(self) -> None:
        self._watchers: Watchers[FileChangeSubscription] = Watchers(FileChangeSubscription)

    @contextmanager
    def subscribe(self, page_id: str) -> Iterator[FileChangeSubscription]:
        """Watch one page's files for as long as the block runs."""
        with self._watchers.watch(page_id) as subscription:
            yield subscription

    def is_watched(self, page_id: str) -> bool:
        return self._watchers.any(page_id)

    async def handle_message(self, body: bytes) -> None:
        """Take one notice off the `musibot.file-changes` exchange."""
        try:
            message = parse_file_change_message(body)
        except ValidationError:
            logger.warning("Dropping an unintelligible message on the file-change exchange")
            return

        reference = message.pipeline_execution
        self.publish(reference.page_id, reference.execution_id, list(message.paths))

    def publish(self, page_id: str, execution_id: int, paths: list[str]) -> None:
        """Offer one notice to whoever is watching that page.

        Synchronous and never awaiting, like the log hub's: this is called from
        the RabbitMQ consumer, and a client that has stopped reading its socket
        must not be able to slow that consumer down.
        """
        if not paths:
            return
        for subscription in self._watchers.of(page_id):
            subscription.offer(execution_id, paths)
