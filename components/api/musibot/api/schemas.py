"""The DTOs of the HTTP API — request and response bodies.

These cross the HTTP boundary, so they are pydantic models. They are the
outward contract of the service and are versioned as such; the internal domain
objects they are built from live in `domain.py`.
"""

from pydantic import BaseModel

from musibot.api.domain import MusicorpusPage, PipelineExecution


class PipelineExecutionView(BaseModel):
    """A *Pipeline Execution* as the API presents it."""

    execution_id: int
    pipeline_name: str
    pipeline_version: str
    state: str
    error: str | None

    @classmethod
    def of(cls, execution: PipelineExecution) -> "PipelineExecutionView":
        return cls(
            execution_id=execution.execution_id,
            pipeline_name=execution.pipeline_name,
            pipeline_version=execution.pipeline_version,
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
