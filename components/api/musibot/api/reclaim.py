"""Freeing a *MusicorpusPage* and everything it holds.

Two callers delete pages — the `DELETE` endpoint, at a *User's* request, and
the public sweep, when a *Public Session* expires — and they must free exactly
the same things. That sequence lives here so the two cannot drift apart: a step
added for one is a step both take.
"""

import asyncio
import logging

from musibot.api.domain import MusicorpusPage, MusicorpusPageRepository, PageNotFound
from musibot.api.executions import ExecutionService
from musibot.api.storage import StoragePort

logger = logging.getLogger(__name__)


async def free_page(
    page: MusicorpusPage,
    repository: MusicorpusPageRepository,
    executions: ExecutionService | None,
    storage: StoragePort | None,
) -> None:
    """Delete a page, stop its executions and clear its folder in MinIO.

    The order matters. Orchestrators are told to stop while the page's
    executions are still known; the page then leaves the repository, so nothing
    can start another execution against it; the *Files* go last, because they
    are the only part a still-running *Worker* may briefly keep writing to (see
    `docs/rough-edges.md`).

    A page already gone is not an error — the sweep works from a snapshot, so a
    *User* may have deleted it in between.
    """
    if executions is not None:
        await executions.terminate_running(page)

    try:
        removed = repository.delete(page.page_id)
    except PageNotFound:
        return

    # The MinIO delete is a blocking boto3 call; keep it off the event loop.
    if storage is not None:
        await asyncio.to_thread(storage.delete_page, removed.page_id)

    logger.info("Freed page %s of %s", removed.page_id, removed.owner)
