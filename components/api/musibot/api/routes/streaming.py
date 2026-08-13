"""What the service's Server-Sent-Events streams have in common.

The frames, the keepalive and the response headers — everything except what is
actually being watched, which is each stream's own business.
"""

from collections.abc import AsyncIterator
from typing import Any

from fastapi.responses import StreamingResponse

KEEPALIVE_SECONDS = 15.0
"""How long a silent stream waits before saying nothing, out loud.

A proxy closes a connection that has been idle too long, and a *Pipeline* that
takes a minute to be picked up is silent for that minute. The comment frame
below costs a dozen bytes and is discarded by every SSE client.
"""

KEEPALIVE_FRAME = b": ping\n\n"

SSE_RESPONSES: dict[int | str, dict[str, Any]] = {200: {"content": {"text/event-stream": {}}}}
"""What these endpoints answer, for the OpenAPI document — which otherwise
advertises the JSON that a `StreamingResponse` never returns."""


def data_frame(payload: str) -> bytes:
    """One SSE event carrying one JSON object."""
    return f"data: {payload}\n\n".encode()


def event_stream(events: AsyncIterator[bytes]) -> StreamingResponse:
    """The response every stream of this service answers with."""
    return StreamingResponse(
        events,
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            # nginx is configured not to buffer these locations anyway; the
            # header says so again for any other proxy in front of it, since a
            # buffered stream is delivered at the end, which is precisely not
            # the point.
            "X-Accel-Buffering": "no",
        },
    )
