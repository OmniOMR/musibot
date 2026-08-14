"""The execution protocols: running *Pipelines* and running *Models*.

Both are the same problem twice — something asks for a named, versioned thing
to be run, without knowing which process will run it — so they share a shape.
See `docs/rabbitmq-exchanges-and-messages.md` for the design and the routing.

These are DTOs: they cross a process boundary, so they are parsed rather than
trusted.
"""

from dataclasses import dataclass
from typing import Annotated, Literal

from pydantic import BaseModel, Discriminator, TypeAdapter

from musibot.core.identifiers import random_id
from musibot.core.page import PageFilePath, PageId

# --- Exchanges (see the wire-protocol document) ------------------------------

PIPELINE_EXECUTIONS_EXCHANGE = "musibot.pipeline-executions"
PIPELINE_EXECUTION_RESULTS_EXCHANGE = "musibot.pipeline-execution-results"
PIPELINE_EXECUTION_CONTROL_EXCHANGE = "musibot.pipeline-execution-control"

MODEL_EXECUTIONS_EXCHANGE = "musibot.model-executions"
MODEL_EXECUTION_CONTROL_EXCHANGE = "musibot.model-execution-control"


def routing_key(name: str, version: str) -> str:
    """Address work to a name and version. Joined with `@`, since a version is
    full of dots and the exchange is `direct`, not `topic`."""
    return f"{name}@{version}"


def generate_model_execution_id() -> str:
    """Make up the ID of one model execution.

    A model execution has no place in the domain model and so no page-scoped
    number to borrow, unlike a *Pipeline Execution*; it carries its own.
    """
    return random_id()


# --- Work queues -------------------------------------------------------------

# Only the queues that *more than one process declares* are here. A queue
# belonging to one process alone — an `api` service's reply queue, a head's
# control queue — is that process's own business and is named where it is
# declared: nobody else can be wrong about it. These two cannot be anybody's own
# business, which is the whole reason they are protocol. See
# `docs/service-configuration.md`, "What is not configuration".

MODEL_WORK_QUEUE_PREFIX = "musibot.model."
PIPELINE_WORK_QUEUE_PREFIX = "musibot.pipeline."
"""Queues are named after what they consume, so that what a queue is for is
evident in the RabbitMQ management UI."""


@dataclass(frozen=True)
class QueueDeclaration:
    """How a queue must be declared, by every process that declares it.

    This is protocol rather than a local decision because RabbitMQ makes it one:
    a second declaration that disagrees with the first is refused outright with
    `PRECONDITION_FAILED`, taking the channel down with it. So a *Worker Head*
    and an *Orchestrator Head* cannot each decide these flags for themselves and
    still work together — which is exactly the test for what belongs in `core`.
    """

    name: str
    exclusive: bool
    auto_delete: bool
    durable: bool


def _work_queue(prefix: str, name: str, version: str) -> QueueDeclaration:
    """The shared queue that everything providing one name and version consumes.

    It is **not exclusive**: being shared by every competing consumer is the
    whole point of it, and is how a *Model* or a *Pipeline* scales horizontally.
    It **auto-deletes**, so a departed provider leaves nothing behind to
    accumulate messages.

    And it is **durable**, which is the one flag that looks wrong. Nothing in
    Musibot is meant to outlive a broker restart — but RabbitMQ 4 refuses a
    transient queue that is not exclusive, and this one cannot be exclusive.
    Durability here costs nothing: the queue still auto-deletes with its last
    consumer, and every message in it is published non-persistent, so a broker
    restart still discards whatever was in flight.
    """
    return QueueDeclaration(
        name=prefix + routing_key(name, version),
        exclusive=False,
        auto_delete=True,
        durable=True,
    )


def model_work_queue(name: str, version: str) -> QueueDeclaration:
    """The queue the *Workers* running one *Model* consume."""
    return _work_queue(MODEL_WORK_QUEUE_PREFIX, name, version)


def pipeline_work_queue(name: str, version: str) -> QueueDeclaration:
    """The queue the *Orchestrators* providing one *Pipeline* consume."""
    return _work_queue(PIPELINE_WORK_QUEUE_PREFIX, name, version)


# --- Shared pieces -----------------------------------------------------------

ExecutionState = Literal["completed", "failed"]
"""How an execution ended. `running` is a state the `api` service tracks; it is
never carried in a result, which by definition reports an ending."""


class NameAndVersion(BaseModel):
    """Identifies a *Pipeline* or a *Model* — never an instance of one."""

    name: str
    version: str


class PipelineExecutionRef(BaseModel):
    """Points at one *Pipeline Execution*.

    Always the pair: execution IDs are unique only within their page, so the
    page ID always travels with one.
    """

    page_id: PageId
    execution_id: int


class OrchestratorRef(BaseModel):
    name: str
    instance_id: str


class WorkerRef(BaseModel):
    name: str
    instance_id: str


# --- Pipeline execution ------------------------------------------------------


class PipelineExecutionStart(BaseModel):
    """Run this *Pipeline* against this page."""

    type: Literal["pipeline-execution-start"] = "pipeline-execution-start"
    page_id: PageId
    execution_id: int
    pipeline: NameAndVersion
    # The *Files* this execution is about, named by the *User*. Unlike the input
    # list of a model execution it does not bound what may be read: a *Pipeline*
    # writes and re-reads intermediate *Files* that nobody could have named,
    # since they do not exist when it starts.
    input: list[PageFilePath] = []
    parameters: dict[str, object] = {}
    timeout_seconds: float


class PipelineExecutionResult(BaseModel):
    """It finished, or it failed."""

    type: Literal["pipeline-execution-result"] = "pipeline-execution-result"
    page_id: PageId
    execution_id: int
    state: ExecutionState
    error: str | None = None
    orchestrator: OrchestratorRef


class PipelineExecutionTerminate(BaseModel):
    """Stop this execution. Fanned out, so it names the execution and each
    *Orchestrator* ignores one it does not have."""

    type: Literal["pipeline-execution-terminate"] = "pipeline-execution-terminate"
    page_id: PageId
    execution_id: int


# --- Model execution ---------------------------------------------------------


class ModelExecutionStart(BaseModel):
    """Run this *Model* against these files."""

    type: Literal["model-execution-start"] = "model-execution-start"
    model_execution_id: str
    model: NameAndVersion
    page_id: PageId
    input: list[PageFilePath] = []
    parameters: dict[str, object] = {}
    # Rides along so that whatever the Model logs can be attributed to the
    # Pipeline Execution that caused it, without the Worker Head asking anyone.
    pipeline_execution: PipelineExecutionRef
    timeout_seconds: float


class ModelExecutionResult(BaseModel):
    """It finished, or it failed."""

    type: Literal["model-execution-result"] = "model-execution-result"
    model_execution_id: str
    state: ExecutionState
    error: str | None = None
    worker: WorkerRef


class ModelExecutionTerminate(BaseModel):
    """Abandon this model execution, if it has not started yet."""

    type: Literal["model-execution-terminate"] = "model-execution-terminate"
    model_execution_id: str


# --- Parsing -----------------------------------------------------------------

# Each exchange carries a known, small set of message types, so a message is
# parsed against the set that can arrive where it was received, discriminated on
# the plain `type` field. There is no cross-exchange union: a pipeline-result
# consumer should reject a model-start message, not silently accept it.

PipelineExecutionMessage = Annotated[
    PipelineExecutionStart | PipelineExecutionResult | PipelineExecutionTerminate,
    Discriminator("type"),
]

ModelExecutionMessage = Annotated[
    ModelExecutionStart | ModelExecutionResult | ModelExecutionTerminate,
    Discriminator("type"),
]

_PIPELINE_ADAPTER: TypeAdapter[
    PipelineExecutionStart | PipelineExecutionResult | PipelineExecutionTerminate
] = TypeAdapter(PipelineExecutionMessage)

_MODEL_ADAPTER: TypeAdapter[
    ModelExecutionStart | ModelExecutionResult | ModelExecutionTerminate
] = TypeAdapter(ModelExecutionMessage)


def parse_pipeline_execution_message(
    payload: str | bytes,
) -> PipelineExecutionStart | PipelineExecutionResult | PipelineExecutionTerminate:
    """Parse a pipeline-execution message, raising `pydantic.ValidationError`
    if it is not one of them."""
    return _PIPELINE_ADAPTER.validate_json(payload)


def parse_model_execution_message(
    payload: str | bytes,
) -> ModelExecutionStart | ModelExecutionResult | ModelExecutionTerminate:
    """Parse a model-execution message, raising `pydantic.ValidationError` if it
    is not one of them."""
    return _MODEL_ADAPTER.validate_json(payload)


def serialize_message(message: BaseModel) -> bytes:
    """Render a message for the wire."""
    return message.model_dump_json().encode("utf-8")
