# Changelog for `api`

Released as `api/vX.Y.Z` git tags — see [Versioning and releases](../../docs/versioning-and-releases.md).

Versions are semver on the **HTTP API**, which is the outward contract for `python-client`, the Web UI and library users. Entries describe that contract and the service's behaviour rather than its internals.


## Unreleased


### Added

- **`GET /musicorpus-pages/{id}/files`** — what a page currently holds, each *File* with its path, size and last-modified time. This is the only way to learn what a *PipelineExecution* produced, since how many staves a page has is what the recognition found out; and, polled while an execution runs, it is how progress is watched until the SSE stream exists. Answered by listing object storage rather than from anything the service remembers, so it stays true across a *File* a later execution overwrote — and, for the same reason, a *File* is not attributed to the execution that wrote it.
- **Public access for the *General public*.** `POST /public-sessions` mints a throwaway bearer token — free and unlimited, and worth nothing on its own: it exists so two members of the public do not see each other's *Musicorpus Pages*. What protects the instance is a pair of global caps on the public tier as one pool (concurrent *Pipeline Executions*, and total MinIO storage), plus a shorter execution deadline; together they bound how much of the *Worker* fleet the public can occupy, which is what keeps a *Library's* batch run from being starved. Sessions expire and their pages are freed with them. Off unless `public_access_enabled` is set, and *Library* tokens are exempt from every cap. See [Public access](../../docs/public-access.md).
- **`429` and `507` on the public tier.** A public caller over the concurrency caps gets `429` with `Retry-After`; over the page cap, `429` without one, since deleting a page helps and waiting does not; with public storage full, `507`. An expired session gets `401`, as an unknown token does; while the session has not yet been swept the message says so, but a client must not branch on that — holding a public session and receiving any `401` is what means "expired, start a new one".


- **`root_path`**, for serving the API under a path prefix. nginx strips the prefix before a request arrives, so routing is unaffected and no ordinary call notices — but the interactive docs at `/docs` are a page that fetches its own schema, and without this they ask the origin root for it and render empty. An instance published at `https://example.org/musibot/api/` sets `root_path=/musibot/api`.
- **`s3_key_prefix` support** (from `core`), so pages can be stored under a prefix within the bucket. Presigning, deleting a page, wiping at startup and measuring the public storage quota all honour it. Two of those changed shape rather than gaining a setting: the startup wipe now empties only what Musibot owns rather than the whole bucket, because a deployment behind a URL prefix has to name its bucket after that prefix and the bucket is therefore the deployment's rather than this service's; and the quota's per-page accounting undoes the rooting before reading a page ID out of a key, which if forgotten would charge every page's bytes to one page named after the prefix. See [Deployment](../../docs/deployment.md).


### Fixed

- **The API token is now an OpenAPI security scheme**, so the interactive docs at `/docs` carry an **Authorize** button and the token is entered once for the whole page. It had been declared as a plain `Authorization` header parameter, which put a field to retype on every endpoint and did not authenticate requests made from the docs.


### Changed

- **Starting a *Pipeline Execution* requires an `input` array** naming the *Files* of the page to process. There is no default and the service will not invent one: it keeps no list of a page's *Files*, and uploads travel over presigned URLs, so it knows which it minted and never which were used. See [Signatures](../../docs/signatures.md).
- **The input list is checked against the announced *Signature*** and a list that does not fit is a `400`, naming the mismatch — twelve staves handed to a one-staff *Model* is refused at the edge instead of failing three hops away.
- **An *ImplicitPipeline* passes the input list straight through** to the *Worker*, rather than substituting the *Model's* declared `signature.input` as the staging list. The service does not expand patterns and does not fan one request out into several; an *ImplicitPipeline* is the *Model* and nothing more.
- **`GET` on an execution reports its `input`.**


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
- **Horizontal scaling.** State lives in-process by design. Moving it to Redis is the known path if it is ever needed.


### Known rough edges

Page eviction policy under disk pressure, stray writes from timed-out executions leaking objects until the next startup wipe, and untested RabbitMQ reconnection recovery — see [Rough edges](../../docs/rough-edges.md).
