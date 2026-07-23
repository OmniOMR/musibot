"""The *MusicorpusPage* endpoints: create, fetch, delete."""

import asyncio
import logging

from fastapi import APIRouter, Depends, Request, status

from musibot.api.auth import current_user, get_owned_page
from musibot.api.domain import MusicorpusPage, MusicorpusPageRepository
from musibot.api.executions import ExecutionService
from musibot.api.schemas import MusicorpusPageView
from musibot.api.storage import StoragePort

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/musicorpus-pages", tags=["musicorpus-pages"])


@router.post("", status_code=status.HTTP_201_CREATED)
def create_page(request: Request, user: str = Depends(current_user)) -> MusicorpusPageView:
    """Create a new, empty *MusicorpusPage* owned by the current *User*."""
    repository: MusicorpusPageRepository = request.app.state.pages
    page = repository.create(owner=user)
    logger.info("Created page %s for user %s", page.page_id, user)
    return MusicorpusPageView.of(page)


@router.get("/{page_id}")
def get_page(page: MusicorpusPage = Depends(get_owned_page)) -> MusicorpusPageView:
    """Fetch a *MusicorpusPage* the current *User* owns."""
    return MusicorpusPageView.of(page)


@router.delete("/{page_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_page(request: Request, page: MusicorpusPage = Depends(get_owned_page)) -> None:
    """Delete a *MusicorpusPage* and free all its resources."""
    repository: MusicorpusPageRepository = request.app.state.pages
    executions: ExecutionService | None = request.app.state.executions
    storage: StoragePort | None = request.app.state.storage

    # Tell orchestrators to stop any running execution before the page vanishes,
    # while its executions are still known.
    if executions is not None:
        await executions.terminate_running(page)

    removed = repository.delete(page.page_id)

    # The MinIO delete is a blocking boto3 call; keep it off the event loop.
    if storage is not None:
        await asyncio.to_thread(storage.delete_page, removed.page_id)

    logger.info("Deleted page %s for user %s", removed.page_id, page.owner)
