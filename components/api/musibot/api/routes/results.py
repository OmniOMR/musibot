"""The execution-result stream: watching every page of one identity."""

import logging
from collections.abc import AsyncIterator
from typing import cast

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse

from musibot.api.auth import Caller, current_user
from musibot.api.public import PublicAccess
from musibot.api.results import ResultHub
from musibot.api.routes import streaming
from musibot.api.schemas import ExecutionResultView

logger = logging.getLogger(__name__)

router = APIRouter(tags=["streams"])


def get_results(request: Request) -> ResultHub:
    return cast(ResultHub, request.app.state.results)


@router.post("/pipeline-execution-results", responses=streaming.SSE_RESPONSES)
async def stream_execution_results(
    request: Request,
    caller: Caller = Depends(current_user),
    hub: ResultHub = Depends(get_results),
) -> StreamingResponse:
    """Stream every *Pipeline Execution* of yours that ends, as it ends.

    Each event's `data` is `{"page_id": ..., "execution": {...}}`, the execution
    being the same shape `GET /musicorpus-pages/{id}/pipeline-executions/{id}`
    answers with, already in its final `completed` or `failed` state.

    The one stream scoped to a *User* rather than a page, because that is who
    wants it: a client holding twenty pages in flight wants one connection
    telling it which have finished, not twenty. A client watching a single page
    filters on `page_id`, which costs it nothing.

    **It carries every page of your identity**, including pages created by
    somebody else holding the same token — Musibot has no sessions, and a
    *Library* token is one identity however many people share it. A client
    therefore watches for the page IDs it created and ignores the rest, which
    it can because it is already obliged to track them. Where a real separation
    is wanted, use two identities; see [the HTTP API docs](../../../../docs/http-api.md).

    Nothing is replayed: an execution that ended before this stream opened is
    not announced on it, and one that ends while the connection is broken is
    missed. So a client **reconciles on connect** — asking about the pages it
    has not yet heard about — and treats this as the thing that saves it from
    polling rather than as the only way it can learn. A watcher that falls a
    thousand results behind is disconnected for the same reason: losing one
    quietly would send a client down a path it has no way to notice.
    """
    identity = caller.identity
    public: PublicAccess = request.app.state.public_access

    async def events() -> AsyncIterator[bytes]:
        with hub.subscribe(identity) as subscription:
            logger.info("A client is watching the executions of %s", identity)
            try:
                while True:
                    if subscription.overrun:
                        logger.warning(
                            "Disconnecting %s, which fell too far behind its results", identity
                        )
                        return

                    result = await subscription.next_result(timeout=streaming.KEEPALIVE_SECONDS)

                    if result is not None:
                        yield streaming.data_frame(ExecutionResultView.of(result).model_dump_json())
                        continue

                    # Nothing to say. A *Public Session* that has ended is the
                    # one thing this stream has to notice by itself: its pages
                    # are swept away and nothing further can ever arrive, while
                    # a *Library* identity is permanent and its stream simply
                    # waits.
                    if caller.is_public and not public.is_live(identity):
                        return
                    yield streaming.KEEPALIVE_FRAME
            finally:
                logger.info("The executions of %s are no longer watched", identity)

    return streaming.event_stream(events())
