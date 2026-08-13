"""The DTOs of the HTTP API — request and response bodies.

These cross the HTTP boundary, so they are pydantic models. They are the
outward contract of the service and are versioned as such; the internal domain
objects they are built from live in `domain.py`.
"""

from datetime import datetime

from musibot.core import PageFilePath
from musibot.core.logs import LogLevel
from pydantic import BaseModel

from musibot.api.discovery import DiscoveryWarning, Listing, PipelineListing, WarningType
from musibot.api.domain import MusicorpusPage, PipelineExecution
from musibot.api.logs import LogLine, SourceKind
from musibot.api.storage import StoredFile


class PipelineExecutionView(BaseModel):
    """A *Pipeline Execution* as the API presents it."""

    execution_id: int
    pipeline_name: str
    pipeline_version: str
    input: list[str]
    state: str
    error: str | None

    @classmethod
    def of(cls, execution: PipelineExecution) -> "PipelineExecutionView":
        return cls(
            execution_id=execution.execution_id,
            pipeline_name=execution.pipeline_name,
            pipeline_version=execution.pipeline_version,
            input=list(execution.input),
            state=execution.state,
            error=execution.error,
        )


class MusicorpusPageView(BaseModel):
    """A *MusicorpusPage* as the API presents it.

    The owner is deliberately not exposed: a *User* only ever sees their own
    pages, so it would be a constant.
    """

    page_id: str
    executions: list[PipelineExecutionView]

    @classmethod
    def of(cls, page: MusicorpusPage) -> "MusicorpusPageView":
        return cls(
            page_id=page.page_id,
            executions=[
                PipelineExecutionView.of(execution)
                for execution in sorted(page.executions.values(), key=lambda e: e.execution_id)
            ],
        )


class LogLineView(BaseModel):
    """One line of a page's log, as one SSE event carries it.

    `seconds` is time since its *Pipeline Execution* started rather than a
    timestamp: what a reader is judging is how long a step took. It is measured
    on the `api` service's clock, the one clock every line passes through.

    Nothing here says which *File* or which *Model* execution a line concerns.
    A log line is text a human reads; a client that wants structure reads the
    execution and the file listing, which are structured on purpose.
    """

    execution_id: int
    seconds: float
    # `worker` and `orchestrator` lines were printed by a *Model* or a
    # *Pipeline*; `api` lines are the service saying what it did with the
    # execution, and are the only ones guaranteed to appear at all.
    kind: SourceKind
    source: str
    level: LogLevel
    message: str

    @classmethod
    def of(cls, line: LogLine) -> "LogLineView":
        return cls(
            execution_id=line.execution_id,
            seconds=line.seconds,
            kind=line.kind,
            source=line.source,
            level=line.level,
            message=line.message,
        )


class PublicSessionView(BaseModel):
    """A freshly minted *Public Session*.

    `expires_at` is fixed at minting and is not extended by use: when it passes,
    the session's pages are freed and every request answers `401`, which the Web
    UI shows as an expired session rather than papering over.
    """

    token: str
    expires_at: datetime


class CreatePipelineExecutionRequest(BaseModel):
    """The *Pipeline* to run against a page, the *Files* to run it over, and any
    parameters for it.

    `input` has no default. The service cannot supply one honestly — it holds no
    list of a page's *Files*, and uploads travel over presigned URLs, so it
    knows which it minted and never which were used. The *User* knows, having
    just uploaded them, and the python client fills it in from what it sent.
    """

    pipeline_name: str
    pipeline_version: str
    input: list[PageFilePath]
    parameters: dict[str, object] = {}


class FileUrlsRequest(BaseModel):
    """The *Files* to get URLs for. Paths are validated as they are parsed, so
    a path escaping the page is rejected before any URL is signed."""

    put: list[PageFilePath] = []
    get: list[PageFilePath] = []


class FileUrlsResponse(BaseModel):
    """Presigned URLs, one per requested *File*, and when they expire."""

    put: dict[str, str] = {}
    get: dict[str, str] = {}
    expires_at: datetime


class FileView(BaseModel):
    """One *File* of a page, as the API presents it.

    `path` is what the *Signature* and the Musicorpus Specification call the
    file — `image.jpg`, `Staves/3/image.jpg` — so it is what a
    *Pipeline Execution*'s `input` is written in and what a URL is asked for.
    """

    path: str
    size: int
    last_modified: datetime

    @classmethod
    def of(cls, file: StoredFile) -> "FileView":
        return cls(path=file.path, size=file.size, last_modified=file.last_modified)


class FileListingResponse(BaseModel):
    """What a page currently holds.

    A *File* and nothing about who wrote it: a page's folder is flat storage
    that any number of *Pipeline Executions* have written into, and a later one
    may overwrite what an earlier one produced. Attributing a *File* to an
    execution would therefore be a guess, and one that goes stale. A caller that
    wants the connection reads it from the executions' *Signatures*.
    """

    files: list[FileView]

    @classmethod
    def of(cls, files: list[StoredFile]) -> "FileListingResponse":
        return cls(files=[FileView.of(file) for file in files])


class NameAndVersionView(BaseModel):
    """Identifies a *Pipeline* — never an instance of one."""

    name: str
    version: str


class SignatureView(BaseModel):
    """The *Files* a *Pipeline* reads and the *Files* it produces."""

    input: list[str] = []
    output: list[str] = []


class PipelineView(BaseModel):
    """One *Pipeline* of the listing, as the API presents it."""

    name: str
    version: str
    signature: SignatureView
    # True when this is an *ImplicitPipeline* — the one Musibot offers for every
    # known *Model*, so that a *Model* can be run in isolation.
    implicit: bool
    orchestrators: list[str] = []
    # How many live announcers are behind this entry. A diagnostic, not a
    # capacity figure: a listed pipeline whose executions all time out is
    # explained by a zero here.
    instances: int

    @classmethod
    def of(cls, pipeline: PipelineListing) -> "PipelineView":
        return cls(
            name=pipeline.name,
            version=pipeline.version,
            signature=SignatureView(
                input=list(pipeline.signature.input),
                output=list(pipeline.signature.output),
            ),
            implicit=pipeline.implicit,
            orchestrators=pipeline.orchestrators,
            instances=pipeline.instances,
        )


class PipelineWarningView(BaseModel):
    """A conflict between announcing providers. `type` is the contract; the
    wording of `message` is not."""

    type: WarningType
    message: str
    pipeline: NameAndVersionView

    @classmethod
    def of(cls, warning: DiscoveryWarning) -> "PipelineWarningView":
        return cls(
            type=warning.type,
            message=warning.message,
            pipeline=NameAndVersionView(name=warning.name, version=warning.version),
        )


class PipelineListingResponse(BaseModel):
    """The answer to `GET /pipelines`.

    Warnings sit at the top level rather than on entries: a conflict is a
    property of the system as a whole, not of any single *Pipeline*.
    """

    pipelines: list[PipelineView]
    warnings: list[PipelineWarningView]

    @classmethod
    def of(cls, listing: Listing) -> "PipelineListingResponse":
        return cls(
            pipelines=[PipelineView.of(pipeline) for pipeline in listing.pipelines],
            warnings=[PipelineWarningView.of(warning) for warning in listing.warnings],
        )
