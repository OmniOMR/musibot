"""What the server sends back, as objects rather than dictionaries.

These mirror the HTTP API's response bodies. They are parsed rather than
trusted — the server is across a network — and they are deliberately forgiving
about fields they do not know, so that a client keeps working against a server
that has grown new ones.
"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class Model(BaseModel):
    model_config = ConfigDict(extra="ignore")


class PageFile(Model):
    """One *File* a *MusicorpusPage* currently holds.

    `path` is the name the *Signature* and the Musicorpus Specification use —
    `image.jpg`, `Staves/3/image.jpg` — so it can be handed straight to
    `download_files` or named as an execution's input.
    """

    path: str
    size: int = 0
    last_modified: datetime | None = None


class PipelineExecution(Model):
    """One execution of a *Pipeline* against a *MusicorpusPage*."""

    execution_id: int
    pipeline_name: str
    pipeline_version: str
    input: list[str] = []
    state: str
    error: str | None = None

    @property
    def is_running(self) -> bool:
        return self.state == "running"

    @property
    def is_completed(self) -> bool:
        return self.state == "completed"


class ExecutionResult(Model):
    """One ended *Pipeline Execution*, as the result stream announces it.

    It names its page because that stream is scoped to a *User* rather than to
    a page: it carries every page of this token's identity, including pages
    another script sharing the token created.
    """

    page_id: str
    execution: PipelineExecution


class MusicorpusPage(Model):
    """A page as the server holds it — its identity and its executions.

    The *Files* are not listed here: they live in object storage and are reached
    through presigned URLs. `MusibotClient.list_files` asks for them.
    """

    page_id: str
    executions: list[PipelineExecution] = []


class Signature(Model):
    """The *Files* a *Pipeline* reads and the *Files* it produces."""

    input: list[str] = []
    output: list[str] = []


class Pipeline(Model):
    """One *Pipeline* that can be run."""

    name: str
    version: str
    signature: Signature = Signature()
    # True when this is the single-*Model* pipeline Musibot offers for every
    # *Model* it knows about, so that a *Model* can be run on its own.
    implicit: bool = False
    orchestrators: list[str] = []
    instances: int = 0


class PipelineWarning(Model):
    """A conflict between providers, reported by the server."""

    type: str
    message: str


class PipelineListing(Model):
    """Everything `GET /pipelines` answers with."""

    pipelines: list[Pipeline] = []
    warnings: list[PipelineWarning] = []
