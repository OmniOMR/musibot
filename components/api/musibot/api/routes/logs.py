"""The log stream endpoint: watching one *MusicorpusPage* being read."""

import logging
from collections.abc import AsyncIterator
from typing import cast

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse

from musibot.api.auth import get_owned_page
from musibot.api.domain import MusicorpusPage, MusicorpusPageRepository, PageNotFound
from musibot.api.logs import LogHub
from musibot.api.schemas import LogLineView

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/musicorpus-pages", tags=["logs"])

KEEPALIVE_SECONDS = 15.0
"""How long a silent stream waits before saying nothing, out loud.

A proxy closes a connection that has been idle too long, and a *Pipeline* that
takes a minute to be picked up is silent for that minute. The comment frame
below costs a dozen bytes and is discarded by every SSE client.
"""


def get_logs(request: Request) -> LogHub:
    return cast(LogHub, request.app.state.logs)


@router.post(
    "/{page_id}/logs",
    responses={200: {"content": {"text/event-stream": {}}, "description": "The page's log"}},
)
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
                    line = await subscription.next_line(timeout=KEEPALIVE_SECONDS)

                    if line is not None:
                        yield f"data: {LogLineView.of(line).model_dump_json()}\n\n".encode()
                        continue

                    # Nothing to say. Check that there is still a page to say it
                    # about — a deleted page is the one ending this stream has to
                    # notice by itself, since nothing further will ever arrive
                    # for it — and then hold the connection open.
                    try:
                        repository.get(page_id)
                    except PageNotFound:
                        return
                    yield b": ping\n\n"
            finally:
                logger.info("The log of page %s is no longer watched", page_id)

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            # nginx is configured not to buffer this location anyway; the header
            # says so again for any other proxy in front of it, since a buffered
            # stream is delivered at the end, which is precisely not the point.
            "X-Accel-Buffering": "no",
        },
    )
