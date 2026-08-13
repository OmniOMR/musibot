"""File changes: what an execution wrote, announced as it is written.

A *Worker Head* uploads a *Model's* output to object storage and then says so
here, so that a *User* learns about a *File* as it appears rather than by asking
again in a second and a half. The `api` service forwards these to whoever is
watching that page; see `docs/rabbitmq-exchanges-and-messages.md`.

The notice carries the *Pipeline Execution* that wrote the *Files*, which is
knowable at this moment and never afterwards: a page's folder is flat storage
that any number of executions write into, and a later one may overwrite what an
earlier one produced — which is why `GET /musicorpus-pages/{id}/files` refuses
to attribute a *File* to an execution at all. A notice is an event, and says who
wrote it *then*; the listing is a state, and does not pretend to know.

Like the log stream, these are fire-and-forget DTOs. Nothing acknowledges them,
and a notice about a page nobody is watching is dropped. Nothing depends on one
arriving: object storage is the truth about what a page holds, and a client that
misses a notice is a poll away from finding out.
"""

from typing import Literal

from pydantic import BaseModel, TypeAdapter

from musibot.core.execution import PipelineExecutionRef
from musibot.core.page import PageFilePath

FILE_CHANGES_EXCHANGE = "musibot.file-changes"


class FilesChanged(BaseModel):
    """*Files* an execution has just written to object storage."""

    type: Literal["files-changed"] = "files-changed"
    pipeline_execution: PipelineExecutionRef
    # The paths written — created or overwritten, which are not told apart
    # because the *Worker Head* detects a change and not its kind. Deletions do
    # not appear here at all: they do not propagate out of a *Model* (see
    # `docs/rough-edges.md`), so an absence in this list means nothing.
    paths: list[PageFilePath] = []


_ADAPTER: TypeAdapter[FilesChanged] = TypeAdapter(FilesChanged)


def parse_file_change_message(payload: str | bytes) -> FilesChanged:
    """Parse a message off the file-change exchange, raising
    `pydantic.ValidationError` if it is not one."""
    return _ADAPTER.validate_json(payload)


def serialize_message(message: BaseModel) -> bytes:
    """Render a message for the wire."""
    return message.model_dump_json().encode("utf-8")
