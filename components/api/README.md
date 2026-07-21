# api

The Web API: the python service that serves the public HTTP API. Every external component talks to it (through nginx). It is the one component that holds state and the one that does not horizontally scale.


## Responsibilities

- Public HTTP API — upload a page, start a pipeline execution, poll or stream status, download the result.
- SSE stream to the Web UI for live progress.
- Holds all system state, which is entirely ephemeral (a page is received, processed within minutes, downloaded, then forgotten).
- Authenticates *Library* users via API tokens kept in a config file. *(Open: general-public auth — a candidate is a token per client IP with rate-limiting.)*

It deliberately does **not** run orchestration or any other heavy logic, so that it can stay a single non-scaled instance. Pipeline execution lives in `orchestrator`.


## Depends on

`core`. At runtime: RabbitMQ and MinIO. State is held in-process today; if it ever needs to scale, that state (essentially MusicorpusPage IDs) moves to Redis.


## Development

`docker compose up` brings it up alongside RabbitMQ and MinIO (see `/deploy`).


## Testing

- Unit tests for the API layer.
- Integration tests against ephemeral RabbitMQ / MinIO (compose or testcontainers).


## Deployment

Installed onto a VM behind nginx (see `docs/deployment.md`).


## Versioning

Semver on the HTTP API — it is an outward contract for `python-client` and library users.
