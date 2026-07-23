"""The *MusicorpusPage* endpoints: create, fetch, delete."""

import logging

from fastapi import APIRouter, Depends, Request, status

from musibot.api.auth import current_user, get_owned_page
from musibot.api.domain import MusicorpusPage, MusicorpusPageRepository
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
def delete_page(request: Request, page: MusicorpusPage = Depends(get_owned_page)) -> None:
    """Delete a *MusicorpusPage* and free its resources.

    Removing it from the repository is what makes it vanish from the API; its
    MinIO folder is then cleared too. Terminating a running *Pipeline Execution*
    is wired in when RabbitMQ dispatch lands.
    """
    repository: MusicorpusPageRepository = request.app.state.pages
    removed = repository.delete(page.page_id)

    storage: StoragePort | None = request.app.state.storage
    if storage is not None:
        storage.delete_page(removed.page_id)

    logger.info("Deleted page %s for user %s", removed.page_id, page.owner)
