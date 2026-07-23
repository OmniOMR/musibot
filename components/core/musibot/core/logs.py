"""The log stream: output from *Models* and *Pipelines*, on its way to a *User*.

Log and progress messages travel straight to the `api` service — not back
through the *Orchestrator* that requested the work — and each names the
*Pipeline Execution* it belongs to. See
`docs/rabbitmq-exchanges-and-messages.md`.

These are fire-and-forget DTOs: nothing acknowledges, retries or orders them,
and one arriving after its *Pipeline Execution* has finished is dropped. They
are for a human watching a page being read, not an audit trail.
"""

from typing import Annotated, Literal

from pydantic import BaseModel, Discriminator, TypeAdapter

from musibot.core.execution import PipelineExecutionRef

LOGS_EXCHANGE = "musibot.logs"

LogLevel = Literal["debug", "info", "warning", "error"]


class LogSource(BaseModel):
    """Where a log line came from — a *Worker* or an *Orchestrator* instance."""

    kind: Literal["worker", "orchestrator"]
    name: str
    instance_id: str


class LogMessage(BaseModel):
    """One line of output from a *Model* or a *Pipeline*."""

    type: Literal["log"] = "log"
    pipeline_execution: PipelineExecutionRef
    source: LogSource
    level: LogLevel = "info"
    message: str
    # An ISO-8601 timestamp, stamped by the source. Kept a plain string: it is
    # only ever displayed, and parsing it would invite a service to reject a log
    # over a malformed clock reading, which is the wrong thing to do with a log.
    timestamp: str | None = None


class ProgressMessage(BaseModel):
    """A fractional progress report for a *Pipeline Execution*."""

    type: Literal["progress"] = "progress"
    pipeline_execution: PipelineExecutionRef
    source: LogSource
    message: str | None = None
    fraction: float | None = None


LogStreamMessage = Annotated[LogMessage | ProgressMessage, Discriminator("type")]

_ADAPTER: TypeAdapter[LogMessage | ProgressMessage] = TypeAdapter(LogStreamMessage)


def parse_log_message(payload: str | bytes) -> LogMessage | ProgressMessage:
    """Parse a message off the log exchange, raising `pydantic.ValidationError`
    if it is neither a log nor a progress message."""
    return _ADAPTER.validate_json(payload)


def serialize_message(message: BaseModel) -> bytes:
    """Render a message for the wire."""
    return message.model_dump_json().encode("utf-8")
