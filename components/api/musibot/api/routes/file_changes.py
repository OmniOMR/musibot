"""The file-change stream endpoint: watching a page's *Files* appear."""

import logging
from collections.abc import AsyncIterator
from typing import cast

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse

from musibot.api.auth import get_owned_page
from musibot.api.domain import MusicorpusPage, MusicorpusPageRepository, PageNotFound
from musibot.api.file_changes import FileChangeHub
from musibot.api.routes import streaming
from musibot.api.schemas import FileChangeView

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/musicorpus-pages", tags=["streams"])


def get_file_changes(request: Request) -> FileChangeHub:
    return cast(FileChangeHub, request.app.state.file_changes)


@router.post("/{page_id}/file-changes", responses=streaming.SSE_RESPONSES)
async def stream_page_file_changes(
    request: Request,
    page: MusicorpusPage = Depends(get_owned_page),
    hub: FileChangeHub = Depends(get_file_changes),
) -> StreamingResponse:
    """Stream the *Files* this page's executions write, as they are written.

    Each event's `data` is one `FileChangeView`: the paths one *Pipeline
    Execution* has just written, created and overwritten alike. Deletions never
    appear — they do not propagate out of a *Model* at all — so this says what
    is new, never what is gone.

    A notice is an **invitation to look**, not a description of the page. What a
    page holds is `GET /musicorpus-pages/{id}/files`, answered from object
    storage; this only says when asking again is worth it. A client that misses
    a notice therefore loses latency and nothing else, which is why nothing is
    replayed and nothing is acknowledged.

    Notices coalesce while a client is not reading: two writes of one path
    between reads arrive as one event naming it once. Since the answer to any
    of them is the same — list the page again — nothing is lost by that, and it
    is what keeps a slow client from accumulating a queue.

    Separate from the [log stream](logs.py) on purpose: that one is text for a
    human and there is a great deal of it, and a client that only wants to know
    about a new *File* should not have to read a deep-learning library's
    warnings to find out. Like it, this is a `POST` because a `GET` invites
    `EventSource`, which cannot send an `Authorization` header.
    """
    page_id = page.page_id
    repository: MusicorpusPageRepository = request.app.state.pages

    async def events() -> AsyncIterator[bytes]:
        with hub.subscribe(page_id) as subscription:
            logger.info("A client is watching the files of page %s", page_id)
            try:
                while True:
                    changes = await subscription.next_changes(timeout=streaming.KEEPALIVE_SECONDS)

                    if changes is None:
                        # Nothing to say. A deleted page is the one ending this
                        # stream has to notice by itself, since nothing further
                        # will ever arrive for it.
                        try:
                            repository.get(page_id)
                        except PageNotFound:
                            return
                        yield streaming.KEEPALIVE_FRAME
                        continue

                    for change in changes:
                        yield streaming.data_frame(FileChangeView.of(change).model_dump_json())
            finally:
                logger.info("The files of page %s are no longer watched", page_id)

    return streaming.event_stream(events())
