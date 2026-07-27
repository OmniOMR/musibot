# Changelog for `api`

Released as `api/vX.Y.Z` git tags — see [Versioning and releases](../../docs/versioning-and-releases.md).

Versions are semver on the **HTTP API**, which is the outward contract for `python-client`, the Web UI and library users. Entries describe that contract and the service's behaviour rather than its internals.


## Unreleased

Nothing yet.


## 0.1.0 — 2026-07-27

First prototype release: enough of the service to take a page from upload to result. Everything below is new.


### Added

- **Pages** — create a *MusicorpusPage*, read it, delete it. State is held in-process and is entirely ephemeral: a page is received, processed, downloaded and forgotten.
- **File transfer by presigned URL** — `POST /musicorpus-pages/{id}/file-urls` issues short-lived URLs that the caller redeems directly against object storage. *File* bytes never pass through this service, which is what keeps the one non-scaling component out of the byte path. The address URLs are issued against is configurable (`s3_public_url`), because in production MinIO is reached at a different address internally than from the internet.
- **Pipeline executions** — start an execution on a page, poll one, list a page's executions. An execution that produces no result before its deadline is declared failed rather than left hanging.
- **Pipeline listing** — `GET /pipelines` and `GET /pipelines/{name}`, assembled from what is currently announced over discovery rather than from any configuration.
- **Discovery registry** — tracks the *Workers* and *Orchestrators* currently alive, with a probe at startup so a freshly started service does not have to wait out a heartbeat interval to know what exists. See [Discovery](../../docs/discovery.md).
- **Implicit pipeline execution** — for every *Model* it knows about, the service offers the single-model *Pipeline* and dispatches it straight to a *Worker*. This is what lets Musibot execute *Models* with no *Orchestrator* deployed at all.
- **Bearer token authentication** for *Library* users, from a JSON file mapping token to identity (`api_tokens_file`), kept separate from the service's dotenv config so secrets carry their own file permissions. Tokens are compared in constant time. With no file configured the service accepts the single development token `secret` and logs a warning that it is doing so.
- **Startup bucket wipe** — storage is scratch space for in-flight pages, so the service clears it on startup.


### Not yet implemented

- **SSE progress stream.** The Web UI and `python-client` poll for execution status; the live stream is not built yet.
- **General-public authentication.** Only *Library* API tokens exist; a token per client IP with rate limiting is the candidate.
- **Horizontal scaling.** State lives in-process by design. Moving it to Redis is the known path if it is ever needed.


### Known rough edges

Page eviction policy under disk pressure, stray writes from timed-out executions leaking objects until the next startup wipe, and untested RabbitMQ reconnection recovery — see [Rough edges](../../docs/rough-edges.md).
