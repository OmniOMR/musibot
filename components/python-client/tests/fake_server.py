"""A Musibot server small enough to live in a test.

It answers over `httpx.MockTransport`, so the client's real request-building,
URL handling and parsing are exercised — only the network is absent. Object
storage answers on a host of its own, exactly as it does in production, because
*File* bytes never travel through the `api` service.
"""

import json
import re
from typing import Any

import httpx

API_HOST = "https://musibot.test/api"
STORAGE_HOST = "https://minio.test"

PAGE_ID = "7Kf2mP9xLwQa"


class FakeServer:
    """The `api` service and object storage, as far as the client can tell."""

    def __init__(
        self,
        *,
        states: list[str] | None = None,
        stored: dict[str, bytes] | None = None,
        start_status: int = 201,
    ):
        # The states successive polls see, so a test can script "running for a
        # while, then completed" without any waiting.
        self._states = states if states is not None else ["completed"]
        self._start_status = start_status

        self.objects: dict[str, bytes] = dict(stored or {})
        self.requests: list[httpx.Request] = []
        self.deleted_pages: list[str] = []
        self.started: list[dict[str, Any]] = []
        self.polls = 0

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

    # --- routing -------------------------------------------------------------

    def _handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        path = request.url.path

        if request.url.host == "minio.test":
            return self._storage(request)

        if request.method == "POST" and path == "/api/musicorpus-pages":
            return httpx.Response(201, json={"page_id": PAGE_ID, "executions": []})

        if request.method == "DELETE" and re.fullmatch(r"/api/musicorpus-pages/[^/]+", path):
            self.deleted_pages.append(path.rsplit("/", 1)[-1])
            return httpx.Response(204)

        if request.method == "GET" and re.fullmatch(r"/api/musicorpus-pages/[^/]+/files", path):
            return self._list_files(path.split("/")[-2])

        if request.method == "POST" and path.endswith("/file-urls"):
            return self._file_urls(request)

        if request.method == "POST" and path.endswith("/pipeline-executions"):
            return self._start_execution(request)

        if request.method == "GET" and re.search(r"/pipeline-executions/\d+$", path):
            return self._poll_execution()

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
        return httpx.Response(
            200,
            json={
                "put": {path: f"{STORAGE_HOST}/bucket/{PAGE_ID}/{path}" for path in body["put"]},
                "get": {path: f"{STORAGE_HOST}/bucket/{PAGE_ID}/{path}" for path in body["get"]},
                "expires_at": "2026-07-25T16:05:00Z",
            },
        )

    def _start_execution(self, request: httpx.Request) -> httpx.Response:
        if self._start_status != 201:
            return httpx.Response(
                self._start_status, json={"detail": "No pipeline or model of that name"}
            )

        body = json.loads(request.content)
        self.started.append(body)
        return httpx.Response(
            201,
            json={
                "execution_id": 1,
                "pipeline_name": body["pipeline_name"],
                "pipeline_version": body["pipeline_version"],
                "input": body["input"],
                "state": "running",
                "error": None,
            },
        )

    def _poll_execution(self) -> httpx.Response:
        state = self._states[min(self.polls, len(self._states) - 1)]
        self.polls += 1
        return httpx.Response(
            200,
            json={
                "execution_id": 1,
                "pipeline_name": "hello-model",
                "pipeline_version": "1.0.0",
                "input": ["image.jpg"],
                "state": state,
                "error": "No staves found in the image." if state == "failed" else None,
            },
        )

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
