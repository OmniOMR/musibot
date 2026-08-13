"""Driving one of the service's SSE streams from a test.

Raw ASGI rather than `TestClient`, because a stream that never ends is exactly
what a buffering test client cannot read: it would wait for a response that is
not coming. Driving the app directly also exercises the parts that matter here —
a client hanging up, and a stream that has to notice its page is gone.
"""

import asyncio
import json
from typing import Any, Self

from fastapi import FastAPI


class Stream:
    """One open stream, driven as the ASGI server would drive it."""

    def __init__(self, app: FastAPI, path: str, token: str):
        self._app = app
        self._path = path
        self._token = token
        self._to_app: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self._from_app: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self._task: asyncio.Task[None] | None = None
        self.status: int | None = None
        self.headers: dict[str, str] = {}

    async def __aenter__(self) -> Self:
        scope = {
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": "POST",
            "path": self._path,
            "raw_path": self._path.encode(),
            "query_string": b"",
            "root_path": "",
            "scheme": "http",
            "server": ("testserver", 80),
            "client": ("testclient", 50000),
            "headers": [
                (b"host", b"testserver"),
                (b"authorization", f"Bearer {self._token}".encode()),
            ],
        }
        await self._to_app.put({"type": "http.request", "body": b"", "more_body": False})
        self._task = asyncio.create_task(self._app(scope, self._receive, self._send))  # type: ignore[arg-type]

        start = await asyncio.wait_for(self._from_app.get(), timeout=2)
        self.status = start["status"]
        self.headers = {key.decode(): value.decode() for key, value in start.get("headers", [])}
        return self

    async def __aexit__(self, *exception: object) -> None:
        # What a browser closing the tab looks like from in here.
        await self._to_app.put({"type": "http.disconnect"})
        if self._task is not None:
            try:
                await asyncio.wait_for(self._task, timeout=2)
            except TimeoutError:
                self._task.cancel()

    async def _receive(self) -> dict[str, Any]:
        return await self._to_app.get()

    async def _send(self, message: dict[str, Any]) -> None:
        await self._from_app.put(message)

    async def next_frame(self, timeout: float = 2.0) -> str:
        """The next chunk the stream writes, whether an event or a keepalive."""
        message = await asyncio.wait_for(self._from_app.get(), timeout=timeout)
        assert message["type"] == "http.response.body", message
        body: bytes = message.get("body", b"")
        return body.decode()

    async def next_event(self, timeout: float = 2.0) -> dict[str, Any]:
        """The next event's data, skipping keepalives."""
        while True:
            frame = await self.next_frame(timeout)
            if frame.startswith(":"):
                continue
            assert frame.startswith("data: ") and frame.endswith("\n\n"), frame
            parsed: dict[str, Any] = json.loads(frame[len("data: ") :])
            return parsed

    async def is_finished(self) -> bool:
        """Whether the app has finished the response on its own."""
        if self._task is None:
            return False
        try:
            await asyncio.wait_for(asyncio.shield(self._task), timeout=1)
        except TimeoutError:
            return False
        return True


def run(scenario: Any) -> None:
    asyncio.run(scenario())
