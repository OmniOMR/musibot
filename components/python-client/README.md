# python-client

Python package that lets external users (libraries, model developers) talk to a Musibot server without touching the raw HTTP API.


## Responsibilities

- Thin, typed wrapper over the `api` service's HTTP API: upload pages, run pipelines, stream progress, download results.
- Batch-friendly helpers for library-scale workloads (millions of pages in bursts).


## Depends on

`core` (for the `MusicorpusPage` model and shared types). Kept light — it installs on end-user machines.


## Development

Develop against a local compose server, or a mocked HTTP layer.


## Testing

- Unit tests against a mocked HTTP layer.
- Optional integration tests against a live compose server.


## Distribution

Published to PyPI — `pip install musibot-client` (name TBD).


## Versioning

Semver, independent of the API's release cadence. This is a public, outward-facing contract.
