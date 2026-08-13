"""The Musibot client: talking to a Musibot server without the raw HTTP API.

Two methods are the interesting ones. :meth:`MusibotClient.process_page` is the
whole round trip for one page — upload it, run a *Pipeline* over it, download
what came out, give the server its resources back — and
:meth:`MusibotClient.process_pages` is that for as many pages as a library has,
several at a time, reporting failures rather than raising them. Everything they
do is also available step by step, for callers who want to hold a page open
across several executions.

*File* bytes never travel through the `api` service. It hands out short-lived
presigned URLs and this client transfers directly to and from object storage,
which is what keeps the one non-scaling service out of the byte path.

Nothing here polls. Waiting for an execution means waiting on one shared stream
of endings (see `results.py`), so a client with twenty pages in flight holds one
connection rather than twenty pollers.
"""

import logging
import threading
from collections.abc import Generator, Iterable, Iterator
from typing import Any, Self

import httpx
from musibot.core import InvalidFilePath, validate_file_path

from musibot.client.batch import (
    BatchJob,
    BatchResult,
    OutputSelector,
    RetryPolicy,
    process_one,
    process_pages,
)
from musibot.client.errors import MusibotApiError, PipelineNotAvailable
from musibot.client.models import (
    ExecutionResult,
    MusicorpusPage,
    PageFile,
    PipelineExecution,
    PipelineListing,
)
from musibot.client.results import RESULTS_PATH, STALL_SECONDS, ResultWatcher, parse_events

logger = logging.getLogger(__name__)

DEFAULT_REQUEST_TIMEOUT_SECONDS = 60.0
"""Per HTTP request. Generous, since one of them uploads a page scan."""

DEFAULT_EXECUTION_TIMEOUT_SECONDS = 600.0
"""How long to wait for a *Pipeline Execution*. Longer than the server's own
timeout, so that the server's verdict is what a caller normally sees."""

DEFAULT_CONCURRENCY = 4
"""How many pages a batch keeps in flight. Sized against the *Worker* fleet
rather than against this client: more pages in flight than there are *Workers*
to read them only lengthens the queue."""


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
        transport: httpx.BaseTransport | None = None,
    ):
        self._base_url = musibot_api_url.rstrip("/")
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
        # Started the first time something waits, and shared by everything that
        # waits after that — a batch of twenty pages included.
        self._results = ResultWatcher(
            self._http, self._base_url, self._auth_headers, self.get_execution
        )

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *exception: object) -> None:
        self.close()

    def close(self) -> None:
        self._results.close()
        self._http.close()

    # --- the whole round trip ------------------------------------------------

    def process_page(
        self,
        # `input` shadows the builtin, deliberately: this is the documented
        # public API and reads as the domain word it is at every call site.
        input: dict[str, bytes],
        pipeline: tuple[str, str],
        output: OutputSelector,
        *,
        parameters: dict[str, Any] | None = None,
        timeout_seconds: float = DEFAULT_EXECUTION_TIMEOUT_SECONDS,
        retry: RetryPolicy | None = None,
    ) -> dict[str, bytes]:
        """Run one page through one *Pipeline* and return the *Files* asked for.

        `input` maps each *File's* path within the page to its bytes, `pipeline`
        is a name and version, and `output` names the *Files* to bring back —
        either outright, or as a predicate over the page's listing for the
        outputs a recognition decides the number of. The execution is run over
        everything `input` uploaded: this method is the whole round trip for one
        page, so what was sent is what there is. A caller holding a page open
        across several executions names the *Files* for each of them with
        :meth:`start_execution` instead.

        Trouble that is not the page's fault — a connection that dropped, a
        service restarting, a `429` — is retried with a backoff; see
        :class:`RetryPolicy`, and pass `RetryPolicy.none()` to try once. A
        *Pipeline* that ran and failed is not retried and raises
        :class:`PipelineExecutionFailed`, because the *Model* answered.

        The page is deleted before returning, whatever happens — including on
        failure. It is the caller's page and nothing else will need it; a server
        left holding it would only evict it later under disk pressure.
        """
        result = process_one(
            self,
            BatchJob(input=input, key=None),
            pipeline,
            output,
            parameters=parameters,
            timeout_seconds=timeout_seconds,
            retry=retry if retry is not None else RetryPolicy(),
        )
        if result.error is not None:
            raise result.error
        return result.files

    def process_pages(
        self,
        jobs: Iterable[BatchJob[Any]],
        pipeline: tuple[str, str],
        output: OutputSelector,
        *,
        concurrency: int = DEFAULT_CONCURRENCY,
        parameters: dict[str, Any] | None = None,
        timeout_seconds: float = DEFAULT_EXECUTION_TIMEOUT_SECONDS,
        retry: RetryPolicy | None = None,
    ) -> Generator[BatchResult[Any], None, None]:
        """Run many pages through one *Pipeline*, yielding results as they finish.

        Built for a whole collection: `jobs` is pulled lazily, one page at a
        time as a worker frees up, so a generator that fetches each scan from an
        image server never has more than `concurrency` of them in memory.

        **Results arrive as pages finish, not in the order they were given.**
        Each carries the `key` its job did, which is how a result is matched
        back to the row, folder or UUID it came from.

        **A failed page is a result, not an exception.** One bad scan among a
        million is not a reason to stop, so `BatchResult.error` carries what
        went wrong and the loop goes on; exceptions are kept for what ends the
        whole run, such as a token the server does not accept.

        ```py
        for result in client.process_pages(jobs(), pipeline=("ayce-long", "…"),
                                           output={"transcription.musicxml"}):
            if result.failed:
                failures.record(result.key, str(result.error))
                continue
            store(result.key, result.files["transcription.musicxml"])
        ```

        Stopping early — a `break`, a `KeyboardInterrupt` — shuts the workers
        down and deletes the pages still in flight.
        """
        yield from process_pages(
            self,
            jobs,
            pipeline,
            output,
            concurrency=concurrency,
            parameters=parameters,
            timeout_seconds=timeout_seconds,
            retry=retry,
        )

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
        stop: threading.Event | None = None,
    ) -> PipelineExecution:
        """Wait until the execution finishes, however it finishes.

        Returns the settled execution whether it completed or failed — deciding
        which of those is acceptable belongs to the caller. Raises
        :class:`PipelineExecutionTimedOut` if this client gave up first, which
        is not the same as the server's own timeout: that one fails the
        execution and comes back as a settled, failed one.

        Nothing is polled. The client holds one stream of endings for all of its
        pages, so waiting on twenty of them costs one connection; a `stop` event
        abandons the wait early, which is how a batch shuts down promptly.
        """
        return self._results.wait_for(
            page_id, execution_id, timeout_seconds=timeout_seconds, stop=stop
        )

    def watch_execution_results(self) -> Iterator[ExecutionResult]:
        """Every *Pipeline Execution* of this token's identity, as it ends.

        The stream `wait_for_execution` uses, offered raw for a caller who wants
        to watch rather than to wait:

        ```py
        for ended in client.watch_execution_results():
            print(ended.page_id, ended.execution.state)
        ```

        It carries **every page of the identity**, including pages another
        script sharing the token created — Musibot has no sessions — so a caller
        that cares about its own pages filters on `page_id`. Nothing is
        replayed: an execution that ended before this was called is not
        announced, so this is for watching what happens next rather than for
        learning what already did.

        The generator ends when the connection does, which for an idle stream
        means when the server or the network says so.
        """
        timeout = httpx.Timeout(connect=10.0, read=STALL_SECONDS, write=10.0, pool=10.0)
        with self._http.stream(
            "POST", self._base_url + RESULTS_PATH, headers=self._auth_headers, timeout=timeout
        ) as response:
            if response.status_code != 200:
                response.read()
                raise MusibotApiError(
                    f"Could not watch execution results: the server answered "
                    f"{response.status_code}",
                    status_code=response.status_code,
                )
            yield from parse_events(response)

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
            retry_after_seconds=_retry_after_of(response),
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


def _retry_after_of(response: httpx.Response) -> float | None:
    """How long the server asked to be left alone, if it said.

    Only the seconds form is read. The HTTP-date form is legal and nothing in
    Musibot sends it, and a client that guessed at a date wrongly would wait
    either far too long or not at all.
    """
    header = response.headers.get("Retry-After")
    if header is None:
        return None
    try:
        return float(header)
    except ValueError:
        return None


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
