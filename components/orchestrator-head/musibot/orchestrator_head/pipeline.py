"""What a *Pipeline* author writes, and the surface they write it against.

A *Pipeline* is a class: it declares what it is called and which *Files* it
reads and writes, and it implements one `async` method that does the work. It is
a class rather than a plain function because the interesting *Pipelines* are
parametrized — the same implementation registered twice under two names, one
pinning a stable *Model* version and the other the one being developed — and
constructor arguments are where those parameters belong. See
`docs/writing-pipelines.md`.

Two different things are called parameters here, and they are not the same:

- **Registration parameters** are constructor arguments, supplied by the
  *Orchestrator* from its own configuration when it registers the *Pipeline*.
  They are fixed for the life of the process and are part of what makes two
  registrations of one class two different *Pipelines*.
- **Execution parameters** are `ctx.parameters`, sent by the *User* with one
  execution request and different every time.

Everything a *Pipeline* may do to the rest of Musibot goes through the
`PipelineContext` it is handed. That indirection is what lets a *Pipeline* be
unit-tested with no broker and no object storage — see
`musibot.orchestrator_head.testing`.
"""

import asyncio
from abc import ABC, abstractmethod
from collections.abc import Callable
from typing import Protocol

from musibot.core.discovery import PipelineDescription, Signature
from musibot.core.execution import NameAndVersion
from musibot.core.logs import LogLevel

from musibot.orchestrator_head.storage import PageStoragePort


class InvalidPipeline(Exception):
    """A *Pipeline* that does not say enough about itself to be announced.

    Raised when it is registered rather than when it is announced, so that a
    misdeclared *Pipeline* stops the *Orchestrator* from starting instead of
    being discovered by a *User* who cannot run it.
    """


class ModelExecutionFailed(Exception):
    """A *Model* this *Pipeline* invoked reported a failure.

    Left to propagate out of `Pipeline.execute` unless the *Pipeline* has
    something better to do about it: the *Orchestrator Head* turns whatever
    comes out of a pipeline into a failed *Pipeline Execution*, and this
    message reaches the *User* who was waiting.
    """

    def __init__(self, model: NameAndVersion, error: str | None):
        self.model = model
        self.error = error
        super().__init__(
            f"The model {model.name!r} version {model.version!r} failed"
            + (f": {error}" if error else "")
        )


class ExecutionRuntime(Protocol):
    """The *Orchestrator Head*, as one running *Pipeline* sees it.

    Everything here reaches the rest of Musibot over RabbitMQ, which is why it
    is a `Protocol`: the runtime that implements it needs a live broker, and a
    test needs an implementation that does not.
    """

    def log(self, message: str, level: LogLevel) -> None:
        """Say one line to whoever is watching this *Pipeline Execution*.

        Fire-and-forget, and deliberately not a coroutine — see `ExecutionLog`.
        """

    def files_written(self, file_paths: list[str]) -> None:
        """Announce *Files* that have just reached object storage."""

    async def execute_model(
        self, model: NameAndVersion, input: list[str], parameters: dict[str, object]
    ) -> None:
        """Run one *Model* and wait for it, raising `ModelExecutionFailed`."""


class ExecutionLog:
    """`ctx.logger`: what a *Pipeline* says while it works.

    The four methods are the ones `logging` has and take `%`-style arguments the
    same way, so that `logger.info("staff %d/%d", n, total)` reads as it does
    anywhere else in python.

    None of them is a coroutine, which is the point. A log line is
    fire-and-forget — nothing acknowledges it, and one about a page nobody is
    watching is dropped — so making a *Pipeline* `await` its own narration would
    buy nothing and clutter every line of it.
    """

    def __init__(self, sink: Callable[[str, LogLevel], None]):
        self._sink = sink

    def debug(self, message: str, *args: object) -> None:
        self._emit(message, args, "debug")

    def info(self, message: str, *args: object) -> None:
        self._emit(message, args, "info")

    def warning(self, message: str, *args: object) -> None:
        self._emit(message, args, "warning")

    def error(self, message: str, *args: object) -> None:
        self._emit(message, args, "error")

    def _emit(self, message: str, args: tuple[object, ...], level: LogLevel) -> None:
        self._sink(message % args if args else message, level)


class PipelineContext:
    """The API a *Pipeline* talks to Musibot through.

    *Files* are fetched from object storage as they are asked for and written
    straight back, rather than mirrored locally the way a *Worker Head* mirrors
    them for its *Model*. A *Pipeline* therefore never holds a stale copy of a
    *File* another *Model* has since rewritten, and never moves bytes it does
    not care about — which matters here and not for a *Model*, because a
    *Pipeline* runs for as long as everything it invokes put together.

    Every storage call is blocking boto3, so each one is run off the event loop.
    That is why they are coroutines while `ctx.logger` is not.
    """

    def __init__(
        self,
        *,
        page_id: str,
        execution_id: int,
        input: list[str],
        parameters: dict[str, object],
        storage: PageStoragePort,
        runtime: ExecutionRuntime,
    ):
        self.page_id = page_id
        """The *MusicorpusPage* this execution is about."""

        self.execution_id = execution_id
        """This execution's number within that page."""

        self.input = input
        """The *Files* the *User* asked to have processed.

        The `api` service has already checked this list against the *Pipeline's*
        declared *Signature*, so it fits the shape that was announced — but
        which *Files* it names is the *User's* choice and only this knows.

        Unlike a *Model's* input list it does not bound what may be read:
        nothing is staged for a *Pipeline*, and it will write and re-read
        intermediate *Files* that did not exist when it started.
        """

        self.parameters = parameters
        """What the *User* sent with this one execution request."""

        self.logger = ExecutionLog(runtime.log)
        """Where a *Pipeline* narrates what it is doing, for a watching *User*."""

        self._storage = storage
        self._runtime = runtime

    # --- files ---------------------------------------------------------------

    async def read_bytes(self, file_path: str) -> bytes:
        """Read one *File* of this page, raising `FileNotInPage` if it is absent."""
        return await asyncio.to_thread(self._storage.read, self.page_id, file_path)

    async def read_text(self, file_path: str, encoding: str = "utf-8") -> str:
        """Read one *File* of this page as text."""
        return (await self.read_bytes(file_path)).decode(encoding)

    async def write_bytes(self, file_path: str, data: bytes) -> None:
        """Write one *File* into this page, and say so.

        The notice on `musibot.file-changes` goes out after the upload and never
        before: a client told about a *File* that has not reached storage yet
        would fetch a `404`, which is a race it could not win.
        """
        await asyncio.to_thread(self._storage.write, self.page_id, file_path, data)
        self._runtime.files_written([file_path])

    async def write_text(self, file_path: str, text: str, encoding: str = "utf-8") -> None:
        """Write one *File* into this page as text."""
        await self.write_bytes(file_path, text.encode(encoding))

    async def list_files(self) -> list[str]:
        """Every *File* this page holds, as page-relative paths.

        This is how a *Pipeline* finds out what a *Model* it ran produced when
        the *Model* was the one inventing the names — a splitter declaring
        `Staves/{*}/image.jpg` decides how many staves there are, and nobody
        else could have known.
        """
        return await asyncio.to_thread(self._storage.list_files, self.page_id)

    async def exists(self, file_path: str) -> bool:
        """Whether this page holds that *File*."""
        return await asyncio.to_thread(self._storage.exists, self.page_id, file_path)

    # --- models --------------------------------------------------------------

    async def execute_model(
        self,
        model: NameAndVersion,
        *,
        input: list[str] | None = None,
        parameters: dict[str, object] | None = None,
    ) -> None:
        """Run one *Model* against this page and wait for it to finish.

        Whatever it produces lands in the page's storage, so there is nothing to
        return — read the *Files* back with `read_bytes` and friends. A *Model*
        that fails raises `ModelExecutionFailed`.

        The *Model* is pinned by name **and** version, exactly. That is what
        makes a *Pipeline* reproducible, and a *Pipeline* that wants to follow a
        moving *Model* takes the version as a registration parameter rather than
        asking for a loose match here.

        Several of these run concurrently in the ordinary way — an
        `asyncio.TaskGroup` over the staves of a page is the shape this exists
        for.
        """
        await self._runtime.execute_model(model, list(input or []), dict(parameters or {}))


class Pipeline(ABC):
    """One *Pipeline* an *Orchestrator* provides.

    Subclass it, set the three attributes below — as class attributes when they
    are fixed, or in `__init__` when they follow from the registration
    parameters — and implement `execute`.
    """

    name: str
    """What a *User* asks for. Must not collide with a *Model's* name, since a
    *Model* is offered as an *ImplicitPipeline* under its own."""

    version: str
    """An opaque string that Musibot never parses, so `4` and `1.2.0` and a date
    are equally good. It is what a *User* pins."""

    signature: Signature
    """Which sets of *Files* this reads and which it writes. Patterns, not
    paths — see `docs/signatures.md`. Without one the *Pipeline* appears in the
    listing as something nobody can construct a request for."""

    @abstractmethod
    async def execute(self, ctx: PipelineContext) -> None:
        """Do the work for one *MusicorpusPage*.

        Raise to fail the *Pipeline Execution*; the exception's message is what
        the *User* is told, so it is worth writing for one.
        """

    def description(self) -> PipelineDescription:
        """What an *Orchestrator* announces about this *Pipeline*."""
        missing = [
            attribute
            for attribute in ("name", "version", "signature")
            if getattr(self, attribute, None) is None
        ]
        if missing:
            raise InvalidPipeline(
                f"{type(self).__name__} does not set {', '.join(missing)}, so it cannot be "
                f"announced. Set them as class attributes or in __init__."
            )

        return PipelineDescription(name=self.name, version=self.version, signature=self.signature)
