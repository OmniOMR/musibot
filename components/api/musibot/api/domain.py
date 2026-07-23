"""The `api` service's in-memory domain model.

These are internal domain objects, built by this service from already-validated
inputs, so they are plain dataclasses rather than pydantic models. The DTOs that
cross the HTTP boundary live in `schemas.py`; the DTOs that cross the RabbitMQ
boundary live in `core`.

All of it is ephemeral. The `MusicorpusPageRepository` holds everything in a
dict today; it exists as a class so that a database or Redis could slot in
behind it later without the rest of the service noticing.
"""

import threading
from dataclasses import dataclass, field
from typing import Literal

from musibot.core import generate_page_id

ExecutionState = Literal["running", "completed", "failed"]


@dataclass
class PipelineExecution:
    """One execution of a *Pipeline* against a *MusicorpusPage*.

    Its ID is a small integer, unique only within its page — reaching one
    already requires access to the page.
    """

    execution_id: int
    pipeline_name: str
    pipeline_version: str
    parameters: dict[str, object]
    state: ExecutionState = "running"
    error: str | None = None


@dataclass
class MusicorpusPage:
    """All the state the service holds for one scanned page.

    The *Files* themselves live in MinIO, not here — this is only the page's
    identity, who owns it, and its executions.
    """

    page_id: str
    owner: str
    executions: dict[int, PipelineExecution] = field(default_factory=dict)
    _next_execution_id: int = 1

    def add_execution(
        self,
        pipeline_name: str,
        pipeline_version: str,
        parameters: dict[str, object],
    ) -> PipelineExecution:
        """Create the next execution for this page and return it."""
        execution = PipelineExecution(
            execution_id=self._next_execution_id,
            pipeline_name=pipeline_name,
            pipeline_version=pipeline_version,
            parameters=parameters,
        )
        self.executions[execution.execution_id] = execution
        self._next_execution_id += 1
        return execution

    def has_running_execution(self) -> bool:
        return any(execution.state == "running" for execution in self.executions.values())


class PageNotFound(KeyError):
    """Raised when a page ID is not in the repository."""


class MusicorpusPageRepository:
    """The in-memory store of every *MusicorpusPage*.

    Guarded by a lock: the HTTP server and the RabbitMQ consumers touch it from
    different threads, and the operations here (create-with-fresh-id,
    add-execution) must not interleave.
    """

    def __init__(self) -> None:
        self._pages: dict[str, MusicorpusPage] = {}
        self._lock = threading.Lock()

    def create(self, owner: str) -> MusicorpusPage:
        """Make a new, empty page owned by the given user."""
        with self._lock:
            # Collisions are astronomically unlikely, but a loop costs nothing
            # and makes "the ID is fresh" a fact rather than a near-certainty.
            while (page_id := generate_page_id()) in self._pages:
                continue
            page = MusicorpusPage(page_id=page_id, owner=owner)
            self._pages[page_id] = page
            return page

    def get(self, page_id: str) -> MusicorpusPage:
        """Return the page, or raise :class:`PageNotFound`."""
        with self._lock:
            try:
                return self._pages[page_id]
            except KeyError:
                raise PageNotFound(page_id)

    def delete(self, page_id: str) -> MusicorpusPage:
        """Remove the page and return it, or raise :class:`PageNotFound`.

        Returning it lets the caller free the page's other resources (its MinIO
        folder, any running execution) now that it is out of the store.
        """
        with self._lock:
            try:
                return self._pages.pop(page_id)
            except KeyError:
                raise PageNotFound(page_id)

    def count(self) -> int:
        with self._lock:
            return len(self._pages)
