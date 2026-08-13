# Python client reference

Every public name in `musibot.client`, what it does and what it costs. The task-shaped introduction is [Using the python client](using-python-client.md); this page is what to reach for once you know what you are building.

Everything here is **synchronous**. Concurrency, where it exists, is threads inside the client — the work is socket waiting, so that is both enough and the thing that runs in a cron script, a notebook and someone else's event loop alike. There is no async client and adding one would mean a second implementation rather than a wrapper; see the [component README](../components/python-client/README.md).


## `MusibotClient`

```py
MusibotClient(
    musibot_api_url: str,
    api_token: str,
    *,
    request_timeout_seconds: float = 60.0,
    transport: httpx.BaseTransport | None = None,
)
```

A connection to one Musibot server on behalf of one *User*. Usable as a context manager, which closes the HTTP connections and the result stream:

```py
with MusibotClient(musibot_api_url="http://localhost:8000/musibot/api", api_token="secret") as client:
    ...
```

`api_token` authenticates against the `api` service **only**. *File* bytes travel directly to and from object storage over presigned URLs, which carry their signature in the query string and are refused if an `Authorization` header is also present — so the token never leaves the one host it belongs to.

`transport` is for tests; it is handed to `httpx` unchanged.

The client is safe to share between threads, which is what its own batch does.


### The whole round trip

#### `process_page(input, pipeline, output, *, parameters=None, timeout_seconds=600.0, retry=None) -> dict[str, bytes]`

One page, start to finish: create it, upload `input`, run `pipeline` over exactly those *Files*, download `output`, delete the page. The page is deleted whatever happens, a failure included.

- `input` — `{path within the page: bytes}`.
- `pipeline` — `(name, version)`. A *Model* run on its own is requested the same way, being an [ImplicitPipeline](domain-model.md).
- `output` — the paths to bring back, or a predicate over the page's listing; see [Choosing outputs](#choosing-outputs).
- `parameters` — passed to the *Pipeline* unchanged.
- `timeout_seconds` — how long **this client** waits. The server has a deadline of its own, and when that one passes the execution comes back failed rather than raising this.
- `retry` — a [`RetryPolicy`](#retrypolicy); the default retries infrastructure trouble.

Raises `PipelineExecutionFailed` if the *Pipeline* ran and failed, `PipelineExecutionTimedOut` if this client gave up first, `PipelineNotAvailable` if nothing provides that pipeline, `MusibotApiError` for anything else.

#### `process_pages(jobs, pipeline, output, *, concurrency=4, parameters=None, timeout_seconds=600.0, retry=None) -> Generator[BatchResult]`

The same for as many pages as you have. See [Batch processing](using-python-client.md#batch-processing-of-many-pages) for the worked examples; the properties that decide how you write the loop are:

- **`jobs` is pulled lazily**, one page at a time as a worker frees up, under a lock. An ordinary generator is therefore safe, and a generator that fetches each scan as it is asked for never has more than `concurrency` of them in memory.
- **Results arrive as pages finish**, not in the order given. Each carries its job's `key`.
- **A failed page is a result, not an exception.** `BatchResult.error` says what went wrong. Exceptions are kept for what ends the whole run.
- **Stopping early stops the run.** A `break` or a `KeyboardInterrupt` shuts the workers down and deletes the pages in flight.
- `concurrency` is how many pages are in flight. Size it against the *Worker* fleet: more pages in flight than there are *Workers* to read them only lengthens a queue.


### Pages

| | |
| --- | --- |
| `create_page() -> MusicorpusPage` | A new, empty page owned by this *User*. |
| `get_page(page_id) -> MusicorpusPage` | The page and its executions. |
| `delete_page(page_id) -> None` | Frees everything it holds, running executions included. |

A page you create is yours to delete. `process_page` and `process_pages` do it for you; holding one open yourself makes it your responsibility, and a server left holding pages evicts them later under disk pressure.


### Files

| | |
| --- | --- |
| `list_files(page_id) -> list[PageFile]` | What the page holds **now**, answered from object storage. |
| `upload_files(page_id, {path: bytes}) -> None` | Straight to object storage over presigned URLs. |
| `download_files(page_id, [path]) -> {path: bytes}` | The same, in the other direction. |
| `file_urls(page_id, *, put=(), get=()) -> {"put": {...}, "get": {...}}` | The presigned URLs themselves, for transferring some other way. |

`list_files` is how outputs are discovered when they cannot be named in advance — how many `Staves/{n}/` folders a page-level recognition produced is its answer rather than yours. It is answered from storage each time rather than from a list the server keeps, so it stays true across a *File* a later execution overwrote.

A path that could leave the page's folder is refused before any request is made.


### Executions

| | |
| --- | --- |
| `start_execution(page_id, name, version, input, parameters=None) -> PipelineExecution` | Starts one and returns immediately. |
| `get_execution(page_id, execution_id) -> PipelineExecution` | Its state now. |
| `list_executions(page_id) -> list[PipelineExecution]` | Every execution of the page. |
| `wait_for_execution(page_id, execution_id, *, timeout_seconds=600.0, stop=None) -> PipelineExecution` | Waits until it ends, however it ends. |
| `watch_execution_results() -> Iterator[ExecutionResult]` | Every ending of this identity, as it happens. |

`input` on `start_execution` is explicit because the server cannot supply it: it keeps no list of a page's *Files*, and uploads travel over presigned URLs it never sees used. You know, having uploaded them.

**Nothing polls.** `wait_for_execution` waits on one stream of endings shared by the whole client, so twenty pages in flight are one connection. It asks about the execution once on the way in, because nothing on that stream is replayed and an execution may have ended already.

`watch_execution_results` is that stream, raw. It carries **every page of this token's identity**, including pages another script sharing the token created — Musibot has no sessions, so filter on `page_id` for your own. Nothing is replayed: it is for watching what happens next, not for learning what already did. See [There are no sessions, only identities](http-api.md#there-are-no-sessions-only-identities).


### Pipelines

#### `list_pipelines() -> PipelineListing`

Everything the server currently knows about, *ImplicitPipelines* included. Assembled from what *Orchestrators* and *Workers* announce, so it can lag reality by a few seconds; `pipeline.instances` is the number of live providers behind an entry, and a listing with zero of them explains executions that time out for no apparent reason.


## Choosing outputs

`output` takes either form:

```py
output={"transcription.musicxml"}                       # exact paths, no listing needed
output=lambda file: file.path.endswith(".musicxml")     # a predicate over list_files
```

The predicate is given each `PageFile` and costs one extra request, which is what buys you the outputs a recognition decides the number of.


## Batch types

### `BatchJob`

```py
BatchJob(input: dict[str, bytes], key: T = None, parameters: dict | None = None)
```

One page's worth of work. `key` is yours and is echoed back untouched — a database UUID, a folder, a whole row object; Musibot never looks at it. `parameters` overrides the batch's for this one page.

### `BatchResult`

```py
result.key          # the job's key
result.page_id      # the page it ran on, even when it failed
result.files        # what was asked for; empty on failure
result.execution    # the settled PipelineExecution, when there was one
result.error        # what went wrong, or None
result.attempts     # how many tries it took
result.seconds      # the whole round trip, retry waits included
result.ok / result.failed
```

`attempts` is worth reading even when it succeeded: a run that quietly took three tries a page is a run with something wrong underneath it.

### `RetryPolicy`

```py
RetryPolicy(
    attempts: int = 6,
    backoff_seconds: float = 1.0,
    max_backoff_seconds: float = 60.0,
    give_up_after_seconds: float = 900.0,
)
RetryPolicy.none()   # try once, report what happens
```

The defaults ride out about a quarter of an hour of trouble. An overnight run over a whole collection can raise `give_up_after_seconds` a long way — the alternative is a second pass in the morning.

**What is retried:** a connection that was refused, reset or never answered; `5xx` from the `api` service or from object storage; `429`, honouring the server's `Retry-After` over the backoff; and this client giving up waiting, since during an outage that is exactly what a page that was waiting looks like.

**What is not:** `PipelineExecutionFailed` — the *Model* answered, and asking again puts the same bytes to the same model — and `400`, `401`, `403`, `404`, which are statements about the request.

A retry starts the page over: a fresh page, a fresh upload, a fresh execution. Recognition is a second or two and a scan is a megabyte, while a page abandoned mid-way through an outage may have been evicted or had its execution time out, so starting again is both the simple thing and the correct one. Every retry logs a warning naming the page, the error and the delay.


## Models

Parsed from the server's responses, and forgiving of fields they do not know so that a client keeps working against a server that has grown some.

| | |
| --- | --- |
| `MusicorpusPage` | `page_id`, `executions` |
| `PipelineExecution` | `execution_id`, `pipeline_name`, `pipeline_version`, `input`, `state`, `error`, and `is_running` / `is_completed` |
| `ExecutionResult` | `page_id`, `execution` — one event of the result stream |
| `PageFile` | `path`, `size`, `last_modified` |
| `Pipeline` | `name`, `version`, `signature`, `implicit`, `orchestrators`, `instances` |
| `Signature` | `input`, `output` — the patterns a *Pipeline* reads and writes, see [Signatures](signatures.md) |
| `PipelineListing` | `pipelines`, `warnings` |


## Errors

```
MusibotError
├── MusibotApiError          the server refused a request; carries status_code
│   └── PipelineNotAvailable nothing provides that pipeline — usually a typo
├── PipelineExecutionFailed  the Pipeline ran and failed; carries page_id, execution_id, error
└── PipelineExecutionTimedOut  this client gave up waiting; the execution may still be running
```

`MusibotApiError.status_code` is `None` when the request never got an answer at all — a refused connection, a name that would not resolve — which is what the retry policy reads as "worth waiting out". `PipelineExecutionFailed.error` is whatever the *Model* or *Pipeline* said, written for a human to read.


## Configuration that is not this client's

Two limits belong to the server and are worth knowing when a batch starts failing:

- **The public tier is capped as one pool** — concurrent executions, storage, page count per session — and a caller over them gets `429` or `507`. A *Library* token is exempt from all of it. See [Public access](public-access.md).
- **A page expires.** Pages are ephemeral by design: processed within minutes, downloaded, forgotten. A batch that holds a page open for an hour is not a supported shape; download and delete.
