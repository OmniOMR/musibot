"""The *Pipeline* listing endpoints.

The listing is not configured anywhere — it is assembled from what
*Orchestrators* and *Workers* announce over RabbitMQ, and it may lag reality by
a few seconds in both directions. See `docs/discovery.md`.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, Request, status

from musibot.api.auth import Caller, current_user
from musibot.api.discovery import ProviderRegistry
from musibot.api.schemas import PipelineListingResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/pipelines", tags=["pipelines"])


def get_registry(request: Request) -> ProviderRegistry:
    registry: ProviderRegistry = request.app.state.providers
    return registry


@router.get("")
def list_pipelines(
    registry: ProviderRegistry = Depends(get_registry),
    caller: Caller = Depends(current_user),
) -> PipelineListingResponse:
    """Every *Pipeline* currently known, *ImplicitPipelines* included."""
    return PipelineListingResponse.of(registry.listing())


@router.get("/{pipeline_name}")
def list_pipeline_versions(
    pipeline_name: str,
    registry: ProviderRegistry = Depends(get_registry),
    caller: Caller = Depends(current_user),
) -> PipelineListingResponse:
    """The versions of one *Pipeline* — what a *User* checks for a newer one."""
    listing = registry.listing()
    listing.pipelines = [
        pipeline for pipeline in listing.pipelines if pipeline.name == pipeline_name
    ]

    if not listing.pipelines:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No such pipeline")

    # Warnings are a property of the system rather than of an entry, so they are
    # carried through unfiltered — a conflict elsewhere is still worth seeing.
    return PipelineListingResponse.of(listing)
