"""A Musibot server small enough to live in a test.

It answers over `httpx.MockTransport`, so the client's real request-building,
URL handling and parsing are exercised — only the network is absent. Object
storage answers on a host of its own, exactly as it does in production, because
*File* bytes never travel through the `api` service.

It also serves the result stream, since the client no longer polls: an execution
ends when this server says so on that stream, which is the path a batch depends
on. How an execution ends is scripted per test rather than timed, so nothing
here waits on a wall clock.
"""

import json
import queue
import re
import threading
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any

import httpx

API_HOST = "https://musibot.test/api"
STORAGE_HOST = "https://minio.test"

PAGE_ID = "7Kf2mP9xLwQa"
"""The first page a test creates. Later ones get an ID of their own, so a batch
can be told apart from the page before it."""

STREAM_IDLE_SECONDS = 2.0
"""How long the result stream waits with nothing at all to say before ending, so
that a test which finishes nothing fails rather than hangs."""

STREAM_TICK_SECONDS = 0.05
"""How often the stream looks for something to announce. Small, because a test
suite should not be paced by it."""


@dataclass
class FakeExecution:
    page_id: str
    execution_id: int
    state: str = "running"
    error: str | None = None
    outcome: str = "completed"
    """What it will settle as, when it settles."""


@dataclass
class FakeServer:
    """The `api` service and object storage, as far as the client can tell."""

    objects: dict[str, bytes] = field(default_factory=dict)
    start_status: int = 201
    outcome: str = "completed"
    """How every execution ends, unless a test says otherwise per page."""

    settle_immediately: bool = False
    """Settle an execution as it starts, so a waiter learns from its first ask
    rather than from the stream. What a page that finished before anyone was
    watching looks like."""

    stream_status: int = 200
    """What the result stream answers, for testing a client that cannot open
    one."""

    auto_finish: bool = True
    """Whether the stream ends a running execution as soon as it notices one.
    Turned off by a test that wants an execution to stay running — one waiting
    to be given up on, say — or that drives `finish` itself."""

    failures: dict[str, int] = field(default_factory=dict)
    """How many times a path should fail before working: `{"/api/musicorpus-pages": 2}`
    makes the next two attempts fail. Keyed by the path a request asks for."""

    failure_status: int = 503

    def __post_init__(self) -> None:
        self.requests: list[httpx.Request] = []
        self.deleted_pages: list[str] = []
        self.started: list[dict[str, Any]] = []
        self.executions: dict[str, FakeExecution] = {}
        self.polls = 0
        self.streams_opened = 0
        self._events: queue.Queue[str] = queue.Queue()
        self._pages = 0
        self._lock = threading.Lock()

    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self._handle)

    @property
    def token(self) -> str | None:
        for request in self.requests:
            if request.url.host == "musibot.test":
                authorization = request.headers.get("Authorization")
                if authorization:
                    return str(authorization)
        return None

    # --- what a test drives --------------------------------------------------

    def finish(self, page_id: str, *, state: str | None = None, error: str | None = None) -> None:
        """End a page's execution and announce it on the result stream."""
        with self._lock:
            execution = self.executions[page_id]
            execution.state = state or execution.outcome
            execution.error = error or (
                "No staves found in the image." if execution.state == "failed" else None
            )
            settled = _execution_json(execution)
        self._events.put(json.dumps({"page_id": page_id, "execution": settled}))

    def unfinished(self) -> list[str]:
        with self._lock:
            return [
                page_id
                for page_id, execution in self.executions.items()
                if execution.state == "running"
            ]

    # --- routing -------------------------------------------------------------

    def _handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        path = request.url.path

        if request.url.host == "minio.test":
            return self._storage(request)

        scripted = self._scripted_failure(path)
        if scripted is not None:
            return scripted

        if request.method == "POST" and path == "/api/musicorpus-pages":
            return httpx.Response(201, json={"page_id": self._new_page(), "executions": []})

        if request.method == "POST" and path == "/api/pipeline-execution-results":
            return self._result_stream()

        if request.method == "DELETE" and re.fullmatch(r"/api/musicorpus-pages/[^/]+", path):
            self.deleted_pages.append(path.rsplit("/", 1)[-1])
            return httpx.Response(204)

        if request.method == "GET" and re.fullmatch(r"/api/musicorpus-pages/[^/]+/files", path):
            return self._list_files(path.split("/")[-2])

        if request.method == "POST" and path.endswith("/file-urls"):
            return self._file_urls(request)

        if request.method == "POST" and path.endswith("/pipeline-executions"):
            return self._start_execution(request, path.split("/")[-2])

        if request.method == "GET" and re.search(r"/pipeline-executions/\d+$", path):
            return self._get_execution(path.split("/")[-3])

        if request.method == "GET" and path == "/api/pipelines":
            return httpx.Response(
                200,
                json={
                    "pipelines": [
                        {
                            "name": "hello-model",
                            "version": "1.0.0",
                            "signature": {
                                "input": ["image.jpg"],
                                "output": ["transcription.musicxml"],
                            },
                            "implicit": True,
                            "orchestrators": [],
                            "instances": 1,
                        }
                    ],
                    "warnings": [],
                },
            )

        return httpx.Response(404, json={"detail": f"No route for {request.method} {path}"})

    # --- handlers ------------------------------------------------------------

    def _scripted_failure(self, path: str) -> httpx.Response | None:
        remaining = self.failures.get(path, 0)
        if remaining <= 0:
            return None
        self.failures[path] = remaining - 1
        if self.failure_status == 0:
            # No answer at all, which is what a dropped connection looks like.
            raise httpx.ConnectError("the connection was refused")
        return httpx.Response(self.failure_status, json={"detail": "try again later"})

    def _new_page(self) -> str:
        with self._lock:
            page_id = PAGE_ID if self._pages == 0 else f"page-{self._pages}"
            self._pages += 1
            return page_id

    def _list_files(self, page_id: str) -> httpx.Response:
        # Answered from the objects storage actually holds, which is how the
        # real service answers it too — it keeps no list of its own.
        prefix = f"{page_id}/"
        return httpx.Response(
            200,
            json={
                "files": [
                    {
                        "path": key[len(prefix) :],
                        "size": len(content),
                        "last_modified": "2026-07-25T16:00:00Z",
                    }
                    for key, content in sorted(self.objects.items())
                    if key.startswith(prefix)
                ]
            },
        )

    def _file_urls(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        page_id = request.url.path.split("/")[-2]
        return httpx.Response(
            200,
            json={
                "put": {path: f"{STORAGE_HOST}/bucket/{page_id}/{path}" for path in body["put"]},
                "get": {path: f"{STORAGE_HOST}/bucket/{page_id}/{path}" for path in body["get"]},
                "expires_at": "2026-07-25T16:05:00Z",
            },
        )

    def _start_execution(self, request: httpx.Request, page_id: str) -> httpx.Response:
        if self.start_status != 201:
            return httpx.Response(
                self.start_status, json={"detail": "No pipeline or model of that name"}
            )

        body = json.loads(request.content)
        self.started.append(body)
        with self._lock:
            execution = FakeExecution(
                page_id=page_id,
                execution_id=1,
                outcome=self.outcome,
            )
            self.executions[page_id] = execution
            started = _execution_json(execution)

        if self.settle_immediately:
            self.finish(page_id)

        return httpx.Response(201, json=started)

    def _get_execution(self, page_id: str) -> httpx.Response:
        self.polls += 1
        with self._lock:
            execution = self.executions.get(page_id)
            if execution is None:
                return httpx.Response(404, json={"detail": "No such execution"})
            return httpx.Response(200, json=_execution_json(execution))

    def _result_stream(self) -> httpx.Response:
        """The endings of this *User's* executions, as Server-Sent Events.

        Anything still running when the stream has nothing else to say is
        finished here, which is what makes a test deterministic without a sleep
        in it: the waiter's first ask sees `running`, and the completion arrives
        down the stream exactly as it does from a real *Worker*.
        """
        self.streams_opened += 1
        if self.stream_status != 200:
            return httpx.Response(self.stream_status, json={"detail": "no"})

        def frames() -> Iterator[bytes]:
            yield b": ping\n\n"
            idle = 0.0
            while True:
                pending = self.unfinished() if self.auto_finish else []
                if pending:
                    # A *Worker* would have finished this one; the stream is
                    # where a client hears about it, which is the path under
                    # test. Doing it here rather than on a timer is what keeps
                    # the suite deterministic and quick.
                    self.finish(pending[0])

                try:
                    payload = self._events.get(timeout=STREAM_TICK_SECONDS)
                except queue.Empty:
                    idle += STREAM_TICK_SECONDS
                    if idle >= STREAM_IDLE_SECONDS:
                        return  # nothing left to say; the client reconnects
                    continue

                idle = 0.0
                yield f"data: {payload}\n\n".encode()

        return httpx.Response(200, content=frames(), headers={"content-type": "text/event-stream"})

    def _storage(self, request: httpx.Request) -> httpx.Response:
        # A presigned URL carries its signature in the query string, and real
        # object storage refuses a request that *also* presents an
        # Authorization header. Refusing it here too keeps the client's API
        # token from leaking onto the storage host unnoticed.
        if "Authorization" in request.headers:
            return httpx.Response(
                400,
                text=(
                    "<Error><Code>InvalidRequest</Code><Message>Only one auth "
                    "mechanism allowed</Message></Error>"
                ),
            )

        # Everything after `/bucket/` is the object key: the page ID and then
        # the File's path within it, which may have folders of its own.
        key = request.url.path.split("/", 2)[-1]

        if request.method == "PUT":
            self.objects[key] = request.content
            return httpx.Response(200)

        content = self.objects.get(key)
        if content is None:
            return httpx.Response(404, text="<Error><Code>NoSuchKey</Code></Error>")
        return httpx.Response(200, content=content)


def _execution_json(execution: FakeExecution) -> dict[str, Any]:
    return {
        "execution_id": execution.execution_id,
        "pipeline_name": "hello-model",
        "pipeline_version": "1.0.0",
        "input": ["image.jpg"],
        "state": execution.state,
        "error": execution.error,
    }
