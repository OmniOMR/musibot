# python-client

Python package that lets external users (libraries, model developers) talk to a Musibot server without touching the raw HTTP API.


## Responsibilities

- Thin, typed wrapper over the `api` service's HTTP API: upload pages, run pipelines, download results.
- Batch-friendly helpers for library-scale workloads (millions of pages in bursts).


## Using it

The whole round trip is one call — see [using the python client](../../docs/using-python-client.md):

```py
from musibot.client import MusibotClient
from pathlib import Path

client = MusibotClient(musibot_api_url="http://localhost:8080", api_token="secret")

output_files = client.process_page(
    input={"image.jpg": Path("my-page-scan.jpg").read_bytes()},
    pipeline=("hello-model", "1.0.0"),
    output={"transcription.musicxml"},
)
```

`process_page` creates a page, uploads the input, starts the *Pipeline Execution*, waits for it, downloads what was asked for, and deletes the page — including when the execution fails, since a failure is no reason to leave a page behind on the server.

Every step is also a method of its own (`create_page`, `upload_files`, `start_execution`, `wait_for_execution`, `download_files`, `delete_page`), for callers who want to hold a page open across several executions or watch progress themselves. `list_pipelines()` answers what is currently available, *ImplicitPipelines* included, and `list_files(page_id)` answers what a page holds — which is how outputs are discovered when they cannot be named in advance, a page-level pipeline finding its own staves.

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


## Not yet implemented

- **The log stream.** `wait_for_execution` polls once a second and says nothing while it waits. The `api` service now streams a page's log over SSE (`POST /musicorpus-pages/{id}/logs`), and this client does not read it yet — so a caller watching a long batch sees nothing of what the *Models* are printing.
- **Batch helpers.** The library-scale burst workflow in the docs is still a TODO.


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
