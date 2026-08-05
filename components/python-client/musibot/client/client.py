"""The Musibot client: talking to a Musibot server without the raw HTTP API.

The interesting method is :meth:`MusibotClient.process_page`, which is the whole
round trip — upload a page, run a *Pipeline* over it, download what came out,
and give the server its resources back. Everything it does is also available
step by step, for callers who want to hold a page open across several
executions or watch progress themselves.

*File* bytes never travel through the `api` service. It hands out short-lived
presigned URLs and this client transfers directly to and from object storage,
which is what keeps the one non-scaling service out of the byte path.
"""

import logging
import time
from collections.abc import Iterable
from typing import Any, Self

import httpx
from musibot.core import InvalidFilePath, validate_file_path

from musibot.client.errors import (
    MusibotApiError,
    PipelineExecutionFailed,
    PipelineExecutionTimedOut,
    PipelineNotAvailable,
)
from musibot.client.models import MusicorpusPage, PageFile, PipelineExecution, PipelineListing

logger = logging.getLogger(__name__)

DEFAULT_REQUEST_TIMEOUT_SECONDS = 60.0
"""Per HTTP request. Generous, since one of them uploads a page scan."""

DEFAULT_EXECUTION_TIMEOUT_SECONDS = 600.0
"""How long to wait for a *Pipeline Execution*. Longer than the server's own
timeout, so that the server's verdict is what a caller normally sees."""

DEFAULT_POLL_INTERVAL_SECONDS = 1.0
"""How often to ask whether an execution has finished. Polling is a placeholder
for the SSE stream that will replace it."""


class MusibotClient:
    """A connection to one Musibot server, on behalf of one *User*.

    Usable as a context manager, which closes the underlying HTTP connections:

    ```py
    with MusibotClient(musibot_api_url=..., api_token=...) as client:
        ...
    ```
    """

    def __init__(
        self,
        musibot_api_url: str,
        api_token: str,
        *,
        request_timeout_seconds: float = DEFAULT_REQUEST_TIMEOUT_SECONDS,
        poll_interval_seconds: float = DEFAULT_POLL_INTERVAL_SECONDS,
        transport: httpx.BaseTransport | None = None,
    ):
        self._base_url = musibot_api_url.rstrip("/")
        self._poll_interval_seconds = poll_interval_seconds
        # Deliberately not a default header on the client: this token
        # authenticates against the `api` service only. Object storage is
        # reached with presigned URLs, which carry their signature in the query
        # string and reject a request that also presents an Authorization
        # header — so sending it there would break every upload and download.
        self._auth_headers = {"Authorization": f"Bearer {api_token}"}
        self._http = httpx.Client(
            timeout=request_timeout_seconds,
            follow_redirects=True,
            transport=transport,
        )

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *exception: object) -> None:
        self.close()

    def close(self) -> None:
        self._http.close()

    # --- the whole round trip ------------------------------------------------

    def process_page(
        self,
        # `input` shadows the builtin, deliberately: this is the documented
        # public API and reads as the domain word it is at every call site.
        input: dict[str, bytes],
        pipeline: tuple[str, str],
        output: Iterable[str],
        *,
        parameters: dict[str, Any] | None = None,
        timeout_seconds: float = DEFAULT_EXECUTION_TIMEOUT_SECONDS,
    ) -> dict[str, bytes]:
        """Run one page through one *Pipeline* and return the *Files* asked for.

        `input` maps each *File's* path within the page to its bytes, `pipeline`
        is a name and version, and `output` names the *Files* to bring back.
        The execution is run over everything `input` uploaded — this method is
        the whole round trip for one page, so what was sent is what there is.
        A caller holding a page open across several executions names the *Files*
        for each of them with :meth:`start_execution` instead.

        The page is deleted before returning, whatever happens — including on
        failure. It is the caller's page and nothing else will need it; a server
        left holding it would only evict it later under disk pressure.
        """
        page = self.create_page()
        try:
            self.upload_files(page.page_id, input)

            name, version = pipeline
            execution = self.start_execution(
                page.page_id, name, version, list(input), parameters or {}
            )
            settled = self.wait_for_execution(
                page.page_id, execution.execution_id, timeout_seconds=timeout_seconds
            )

            if not settled.is_completed:
                raise PipelineExecutionFailed(
                    f"Pipeline {name!r} version {version!r} failed: "
                    f"{settled.error or 'no reason given'}",
                    page_id=page.page_id,
                    execution_id=settled.execution_id,
                    error=settled.error,
                )

            return self.download_files(page.page_id, output)
        finally:
            # Best-effort: a page that cannot be deleted is the server's problem
            # to evict, and saying so would replace the caller's real error with
            # a worse one.
            try:
                self.delete_page(page.page_id)
            except Exception:
                logger.warning("Could not delete page %s", page.page_id, exc_info=True)

    # --- pages ---------------------------------------------------------------

    def create_page(self) -> MusicorpusPage:
        """Create a new, empty *MusicorpusPage* owned by this *User*."""
        return MusicorpusPage.model_validate(self._request("POST", "/musicorpus-pages").json())

    def get_page(self, page_id: str) -> MusicorpusPage:
        return MusicorpusPage.model_validate(
            self._request("GET", f"/musicorpus-pages/{page_id}").json()
        )

    def delete_page(self, page_id: str) -> None:
        """Delete a page and free everything it holds, running executions included."""
        self._request("DELETE", f"/musicorpus-pages/{page_id}")

    # --- files ---------------------------------------------------------------

    def list_files(self, page_id: str) -> list[PageFile]:
        """The *Files* the page currently holds.

        What a *Pipeline* produced is not known in advance — a page-level run
        writes a `Staves/{n}/` folder whose size depends on the page — so this
        is how outputs are discovered before they are downloaded:

            for file in client.list_files(page_id):
                print(file.path, file.size)

        Answered from storage rather than from anything the server remembers, so
        it stays true across a *File* a later execution overwrote.
        """
        response = self._request("GET", f"/musicorpus-pages/{page_id}/files").json()
        return [PageFile.model_validate(file) for file in response.get("files", [])]

    def file_urls(
        self,
        page_id: str,
        *,
        put: Iterable[str] = (),
        get: Iterable[str] = (),
    ) -> dict[str, dict[str, str]]:
        """Ask for presigned URLs to upload and download *Files* directly."""
        put_paths = [_checked(path) for path in put]
        get_paths = [_checked(path) for path in get]
        if not put_paths and not get_paths:
            return {"put": {}, "get": {}}

        response = self._request(
            "POST",
            f"/musicorpus-pages/{page_id}/file-urls",
            json={"put": put_paths, "get": get_paths},
        ).json()
        return {"put": response.get("put", {}), "get": response.get("get", {})}

    def upload_files(self, page_id: str, files: dict[str, bytes]) -> None:
        """Upload *Files* straight to object storage."""
        if not files:
            return

        urls = self.file_urls(page_id, put=files.keys())["put"]
        for file_path, content in files.items():
            url = urls.get(file_path)
            if url is None:
                raise MusibotApiError(f"The server issued no upload URL for {file_path!r}")
            response = self._http.put(url, content=content)
            _raise_for_storage_status(response, file_path, "upload")

    def download_files(self, page_id: str, file_paths: Iterable[str]) -> dict[str, bytes]:
        """Download *Files* straight from object storage."""
        paths = list(file_paths)
        if not paths:
            return {}

        urls = self.file_urls(page_id, get=paths)["get"]
        downloaded: dict[str, bytes] = {}
        for file_path in paths:
            url = urls.get(file_path)
            if url is None:
                raise MusibotApiError(f"The server issued no download URL for {file_path!r}")
            response = self._http.get(url)
            _raise_for_storage_status(response, file_path, "download")
            downloaded[file_path] = response.content
        return downloaded

    # --- executions ----------------------------------------------------------

    def start_execution(
        self,
        page_id: str,
        pipeline_name: str,
        pipeline_version: str,
        input: Iterable[str],
        parameters: dict[str, Any] | None = None,
    ) -> PipelineExecution:
        """Start a *Pipeline Execution* against a page and return immediately.

        `input` names the *Files* of the page to process. It is explicit because
        the server cannot supply it — it keeps no list of a page's *Files*, and
        uploads go straight to object storage over presigned URLs, so it never
        learns which of them were used. The caller knows, having uploaded them.
        For the common case :meth:`process_page` fills this in.
        """
        response = self._request(
            "POST",
            f"/musicorpus-pages/{page_id}/pipeline-executions",
            json={
                "pipeline_name": pipeline_name,
                "pipeline_version": pipeline_version,
                "input": list(input),
                "parameters": parameters or {},
            },
        )
        return PipelineExecution.model_validate(response.json())

    def get_execution(self, page_id: str, execution_id: int) -> PipelineExecution:
        return PipelineExecution.model_validate(
            self._request(
                "GET", f"/musicorpus-pages/{page_id}/pipeline-executions/{execution_id}"
            ).json()
        )

    def list_executions(self, page_id: str) -> list[PipelineExecution]:
        response = self._request("GET", f"/musicorpus-pages/{page_id}/pipeline-executions").json()
        return [PipelineExecution.model_validate(entry) for entry in response]

    def wait_for_execution(
        self,
        page_id: str,
        execution_id: int,
        *,
        timeout_seconds: float = DEFAULT_EXECUTION_TIMEOUT_SECONDS,
    ) -> PipelineExecution:
        """Poll until the execution finishes, however it finishes.

        Returns the settled execution whether it completed or failed — deciding
        which of those is acceptable belongs to the caller. Polling is what the
        SSE stream will replace.
        """
        deadline = time.monotonic() + timeout_seconds

        while True:
            execution = self.get_execution(page_id, execution_id)
            if not execution.is_running:
                return execution

            if time.monotonic() >= deadline:
                raise PipelineExecutionTimedOut(
                    f"Gave up waiting for execution {execution_id} of page {page_id} "
                    f"after {timeout_seconds:.0f}s; it may still be running",
                    page_id=page_id,
                    execution_id=execution_id,
                )

            time.sleep(self._poll_interval_seconds)

    # --- pipelines -----------------------------------------------------------

    def list_pipelines(self) -> PipelineListing:
        """Every *Pipeline* the server currently knows about.

        Assembled from what *Orchestrators* and *Workers* announce, so it may
        lag reality by a few seconds — and it includes one entry per *Model*,
        for running a *Model* on its own.
        """
        return PipelineListing.model_validate(self._request("GET", "/pipelines").json())

    # --- internals -----------------------------------------------------------

    def _request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        url = self._base_url + path
        try:
            response = self._http.request(method, url, headers=self._auth_headers, **kwargs)
        except httpx.RequestError as error:
            raise MusibotApiError(f"Could not reach the Musibot server at {url}: {error}")

        if response.is_success:
            return response

        detail = _detail_of(response)

        if response.status_code == 404 and "pipeline-executions" in path and method == "POST":
            # Starting a Pipeline nobody provides, rather than a missing page.
            raise PipelineNotAvailable(detail, status_code=404)

        raise MusibotApiError(
            f"{method} {path} failed with {response.status_code}: {detail}",
            status_code=response.status_code,
        )


def _checked(file_path: str) -> str:
    """Reject a path that could not name a *File* inside a page.

    Checked here as well as on the server so that an obvious mistake is a plain
    error at the call site rather than a rejected request.
    """
    try:
        return validate_file_path(file_path)
    except InvalidFilePath as error:
        raise MusibotApiError(str(error))


def _detail_of(response: httpx.Response) -> str:
    try:
        body = response.json()
    except ValueError:
        return response.text[:200]
    if isinstance(body, dict) and "detail" in body:
        return str(body["detail"])
    return str(body)[:200]


def _raise_for_storage_status(response: httpx.Response, file_path: str, action: str) -> None:
    """Object storage answers directly, so its failures are reported as its own.

    A missing *File* is a `404` straight from MinIO, which is worth saying
    plainly: it usually means the *Pipeline* did not produce what was asked for.
    """
    if response.is_success:
        return
    # Object storage explains itself in the body, and that explanation is the
    # whole diagnosis when a presigned URL is refused — so it is carried along
    # rather than reduced to a status code.
    raise MusibotApiError(
        f"Could not {action} {file_path!r}: object storage answered "
        f"{response.status_code}: {response.text[:300]}",
        status_code=response.status_code,
    )
