"""The *Pipeline Execution* endpoints: start, list, fetch."""

import logging

from fastapi import APIRouter, Depends, HTTPException, Request, status

from musibot.api.auth import get_owned_page
from musibot.api.domain import MusicorpusPage
from musibot.api.executions import ExecutionService
from musibot.api.schemas import CreatePipelineExecutionRequest, PipelineExecutionView

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/musicorpus-pages", tags=["pipeline-executions"])


def get_executions(request: Request) -> ExecutionService:
    executions: ExecutionService | None = request.app.state.executions
    if executions is None:
        # Running without RabbitMQ configured — pages and files work, but
        # nothing can be executed.
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Pipeline execution is not available (no message broker configured)",
        )
    return executions


@router.post("/{page_id}/pipeline-executions", status_code=status.HTTP_201_CREATED)
async def start_pipeline_execution(
    body: CreatePipelineExecutionRequest,
    page: MusicorpusPage = Depends(get_owned_page),
    executions: ExecutionService = Depends(get_executions),
) -> PipelineExecutionView:
    """Start a *Pipeline Execution* against this page."""
    execution = await executions.start(
        page, body.pipeline_name, body.pipeline_version, body.parameters
    )
    return PipelineExecutionView.of(execution)


@router.get("/{page_id}/pipeline-executions")
def list_pipeline_executions(
    page: MusicorpusPage = Depends(get_owned_page),
) -> list[PipelineExecutionView]:
    """List this page's completed and running *Pipeline Executions*."""
    return [
        PipelineExecutionView.of(execution)
        for execution in sorted(page.executions.values(), key=lambda e: e.execution_id)
    ]


@router.get("/{page_id}/pipeline-executions/{execution_id}")
def get_pipeline_execution(
    execution_id: int,
    page: MusicorpusPage = Depends(get_owned_page),
) -> PipelineExecutionView:
    """Fetch one *Pipeline Execution* — the endpoint a client polls."""
    execution = page.executions.get(execution_id)
    if execution is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No such execution")
    return PipelineExecutionView.of(execution)
