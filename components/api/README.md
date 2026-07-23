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

Install into a virtual environment (with `core` alongside it, from its path) and run the service:

```bash
cd components/api
python3 -m venv .venv
.venv/bin/pip install -e ../core -e '.[dev]'
.venv/bin/musibot-api
```

With no configuration it comes up on `127.0.0.1:8080` and accepts the single development token `secret` (matching the docs and the [local stack](../../deploy/README.md)) — it logs a warning that it is doing so. `docker compose up` in `/deploy` brings up the RabbitMQ and MinIO it will talk to.


### API tokens

Each *Library* user authenticates with a bearer token. The tokens are configured as a JSON file mapping token to user identity, pointed at by `api_tokens_file` / `MUSIBOT_API_TOKENS_FILE`:

```json
{ "s3cr3t-token-for-alice": "alice", "another-token-for-bob": "bob" }
```

It is a separate file from the service's dotenv config so the secrets are not mixed in with ordinary settings and can carry their own file permissions. When unset, the built-in `secret` → `developer` token is used, for development only.


## Testing

- Unit tests for the API layer, driven through FastAPI's `TestClient` — no RabbitMQ or MinIO needed.
- Integration tests against ephemeral RabbitMQ / MinIO (compose or testcontainers) as those integrations land.

```bash
.venv/bin/python -m pytest
.venv/bin/python -m ruff check .
.venv/bin/python -m ruff format --check .
.venv/bin/python -m mypy
```


## Deployment

Installed onto a VM behind nginx (see `docs/deployment.md`).


## Versioning

Semver on the HTTP API — it is an outward contract for `python-client` and library users.
