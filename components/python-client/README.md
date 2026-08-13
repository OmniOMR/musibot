# python-client

Python package that lets external users (libraries, model developers) talk to a Musibot server without touching the raw HTTP API.


## Responsibilities

- Thin, typed wrapper over the `api` service's HTTP API: upload pages, run pipelines, download results.
- Batch processing for library-scale workloads: many pages in flight, results as they finish, failures reported rather than raised, and infrastructure trouble waited out.


## Using it

The whole round trip is one call — see [using the python client](../../docs/using-python-client.md):

```py
from musibot.client import MusibotClient
from pathlib import Path

client = MusibotClient(musibot_api_url="http://localhost:8000/musibot/api", api_token="secret")

output_files = client.process_page(
    input={"image.jpg": Path("my-page-scan.jpg").read_bytes()},
    pipeline=("hello-model", "1.0.0"),
    output={"transcription.musicxml"},
)
```

`process_page` creates a page, uploads the input, starts the *Pipeline Execution*, waits for it, downloads what was asked for, and deletes the page — including when the execution fails, since a failure is no reason to leave a page behind on the server.

A whole collection is `process_pages`, which is the same round trip several pages at a time — see [the reference](../../docs/python-client-reference.md) and the [batch guide](../../docs/using-python-client.md#batch-processing-of-many-pages).

Every step is also a method of its own (`create_page`, `upload_files`, `start_execution`, `wait_for_execution`, `download_files`, `delete_page`), for callers who want to hold a page open across several executions. `list_pipelines()` answers what is currently available, *ImplicitPipelines* included, and `list_files(page_id)` answers what a page holds — which is how outputs are discovered when they cannot be named in advance, a page-level pipeline finding its own staves.

*File* bytes never pass through the `api` service: it issues short-lived presigned URLs and this client transfers directly to and from object storage, which is what keeps the one non-scaling service out of the byte path.


## Depends on

`core` (for page path validation and shared types) and `httpx`. Kept light — it installs on end-user machines.


## Development

```bash
cd components/python-client
python3 -m venv .venv
.venv/bin/pip install -e ../core -e '.[dev]'
```


## Testing

Unit tests run against a fake Musibot server on an `httpx.MockTransport`, so the client's real request building, URL handling and parsing are exercised and only the network is absent. Object storage answers on a host of its own there, exactly as in production.

```bash
.venv/bin/python -m pytest
.venv/bin/python -m ruff check .
.venv/bin/python -m ruff format --check .
.venv/bin/python -m mypy
```


## Threads, and why there is no async client

Concurrency here is threads: a worker per page in flight, plus one thread holding the result stream. The work is socket waiting, so the GIL is released throughout, and the useful number of pages in flight is bounded by the *Worker* fleet rather than by anything in this process.

An async core with sync wrappers was considered and rejected. **Both ends of this API are the caller's blocking code** — the generator that fetches a scan from an image server, and the loop body that writes to Solr or to disk — so an async core would have to push both onto threads anyway or stall the event loop, streamed results included. Sync-over-async does not remove threads either: a client that keeps a connection pool and a stream alive across calls needs a background loop thread, which is a thread with extra steps, and it is fragile for a caller already inside a loop.

If a genuinely async caller ever turns up, the answer is an `AsyncMusibotClient` written as a **sibling** — the HTTP surface is small enough to have twice, which is what httpx itself does — rather than either one wrapping the other.


## Not yet implemented

- **The log and file-change streams.** The client reads `POST /pipeline-execution-results`, which is what replaced its polling, but not the two page-scoped streams: a caller cannot yet watch what a *Model* is printing about their page, or be told a *File* has appeared before the execution ends. Both are page-scoped, so they are one connection per page rather than one per client, which is why a batch does not want them by default.


## Distribution

Not published to PyPI yet. While Musibot is on `0.x` and only the team is running it, releases are git tags and the client is installed from a git link — note that `musibot-core` has to be given explicitly, since it is not on any index either:

```bash
pip install \
  'musibot-core @ git+https://github.com/OmniOMR/musibot.git@core/v0.1.0#subdirectory=components/core' \
  'musibot-client @ git+https://github.com/OmniOMR/musibot.git@python-client/v0.1.0#subdirectory=components/python-client'
```

This is the component most likely to go to PyPI first, as `musibot-client`, once there are users outside the team. See [Versioning and releases](../../docs/versioning-and-releases.md).


## Versioning

Semver, independent of the API's release cadence. This is a public, outward-facing contract. The version is derived from the `python-client/v*` git tags rather than written into `pyproject.toml`; see [Versioning and releases](../../docs/versioning-and-releases.md).
