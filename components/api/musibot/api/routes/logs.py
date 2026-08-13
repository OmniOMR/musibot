"""The log stream endpoint: watching one *MusicorpusPage* being read."""

import logging
from collections.abc import AsyncIterator
from typing import cast

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse

from musibot.api.auth import get_owned_page
from musibot.api.domain import MusicorpusPage, MusicorpusPageRepository, PageNotFound
from musibot.api.logs import LogHub
from musibot.api.routes import streaming
from musibot.api.schemas import LogLineView

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/musicorpus-pages", tags=["streams"])


def get_logs(request: Request) -> LogHub:
    return cast(LogHub, request.app.state.logs)


@router.post("/{page_id}/logs", responses=streaming.SSE_RESPONSES)
async def stream_page_log(
    request: Request,
    page: MusicorpusPage = Depends(get_owned_page),
    hub: LogHub = Depends(get_logs),
) -> StreamingResponse:
    """Stream everything logged for this page, as Server-Sent Events.

    One stream per *MusicorpusPage* rather than per *Pipeline Execution*: a page
    may be read several times, and somebody debugging a reading wants the whole
    story in the order it happened rather than two of them to interleave by
    hand. Each event names the execution it belongs to.

    Each event's `data` is one `LogLineView` as JSON. Comment frames (`: ping`)
    arrive on an idle stream and are ignored by any SSE client.

    Nothing is replayed. Lines produced while nobody was watching are gone — a
    log here is a *User* watching a page being read, not an audit trail — so a
    client that wants the whole log opens this before starting an execution.

    Log lines and [file changes](file_changes.py) are separate streams on
    purpose: this one is text for a human and there is a great deal of it, most
    of it a deep-learning library's warnings, and a client that only wants to
    know about a new *File* should not have to read it all.

    > **Why `POST`.** A `GET` would invite `EventSource`, which cannot send an
    > `Authorization` header, and the usual way round that is to put the token
    > in the query string, where it lands in proxy logs and browser history.
    > This service authenticates every request the same way, so the endpoint is
    > a `POST` and a browser reads it with `fetch`.
    """
    page_id = page.page_id
    repository: MusicorpusPageRepository = request.app.state.pages

    async def events() -> AsyncIterator[bytes]:
        with hub.subscribe(page_id) as subscription:
            logger.info("A client is watching the log of page %s", page_id)
            try:
                while True:
                    line = await subscription.next_line(timeout=streaming.KEEPALIVE_SECONDS)

                    if line is not None:
                        yield streaming.data_frame(LogLineView.of(line).model_dump_json())
                        continue

                    # Nothing to say. Check that there is still a page to say it
                    # about — a deleted page is the one ending this stream has to
                    # notice by itself, since nothing further will ever arrive
                    # for it — and then hold the connection open.
                    try:
                        repository.get(page_id)
                    except PageNotFound:
                        return
                    yield streaming.KEEPALIVE_FRAME
            finally:
                logger.info("The log of page %s is no longer watched", page_id)

    return streaming.event_stream(events())
