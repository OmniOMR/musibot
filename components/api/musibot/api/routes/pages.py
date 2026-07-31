"""The *MusicorpusPage* endpoints: create, fetch, delete."""

import logging

from fastapi import APIRouter, Depends, Request, status

from musibot.api.auth import Caller, current_user, get_owned_page
from musibot.api.domain import MusicorpusPage, MusicorpusPageRepository
from musibot.api.executions import ExecutionService
from musibot.api.public import PublicAccess
from musibot.api.reclaim import free_page
from musibot.api.schemas import MusicorpusPageView
from musibot.api.storage import StoragePort

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/musicorpus-pages", tags=["musicorpus-pages"])


@router.post("", status_code=status.HTTP_201_CREATED)
def create_page(request: Request, caller: Caller = Depends(current_user)) -> MusicorpusPageView:
    """Create a new, empty *MusicorpusPage* owned by the current caller."""
    repository: MusicorpusPageRepository = request.app.state.pages
    public: PublicAccess = request.app.state.public_access

    # Checked before the page exists, so a refusal leaves nothing behind. A
    # *Library* user passes straight through; only the public tier is capped.
    public.check_may_create_page(caller.identity)

    page = repository.create(owner=caller.identity)
    logger.info("Created page %s for %s", page.page_id, caller.identity)
    return MusicorpusPageView.of(page)


@router.get("/{page_id}")
def get_page(page: MusicorpusPage = Depends(get_owned_page)) -> MusicorpusPageView:
    """Fetch a *MusicorpusPage* the current caller owns."""
    return MusicorpusPageView.of(page)


@router.delete("/{page_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_page(request: Request, page: MusicorpusPage = Depends(get_owned_page)) -> None:
    """Delete a *MusicorpusPage* and free all its resources."""
    repository: MusicorpusPageRepository = request.app.state.pages
    executions: ExecutionService | None = request.app.state.executions
    storage: StoragePort | None = request.app.state.storage

    await free_page(page, repository, executions, storage)
