# HTTP API

This page provides a high-level overview of the HTTP API that the `api` service exposes to public.


## Authentication

Requests to the API are authorized with a bearer token, given to the *User* manually. Existing known API tokens are listed in the `api` service's configuration file. Each *User* is identified by their token and may only access *Musicorpus Pages* they created; requests touching another user's page are rejected.

The *general public* gets a token too, minted on demand by `POST /public-sessions` and carried in the same header. It identifies a *Public Session* rather than a person — minting is free and unlimited, and it exists only so that two members of the public do not see each other's pages. What protects the instance is a set of caps on the public tier as a whole, not on any one session; see [Public access](public-access.md). An instance that does not offer public access answers `404` to the minting endpoint.

The token is declared as an OpenAPI security scheme, so the interactive docs the service serves at `/docs` carry an **Authorize** button: paste the token once there and every request from that page is authenticated, which is the quickest way to try the API by hand.


### There are no sessions, only identities

A token resolves to an **identity**, and a *MusicorpusPage* belongs to that identity — not to the connection, the process, or the run that created it. Musibot has no concept of a session for a *Library* user, and deliberately so: it would be a lifetime to manage, an expiry to explain and a thing to resume, for a system whose entire state is already discarded within the hour.

The consequence is worth stating plainly, because it decides what a client must do. **Two people using one *Library's* token share everything that token owns** — one running a production batch over a whole collection, another testing next month's model, both `ufal`. Neither's pages are hidden from the other, and neither is protected from the other deleting one.

So **a client tracks the page IDs it created** and works only with those. That is not an extra obligation: no endpoint answers "all pages of this identity" — the Web UI keeps its own ledger in the browser, the python client keeps its own bookkeeping, and both need it anyway to know what to download. Page IDs are 12-character NanoIDs, so two clients never collide.

Where a real separation is wanted, give the two uses **different identities** rather than reaching for sessions:

```json
{ "token-for-the-batch-run": "ufal", "token-for-development": "ufal-dev" }
```

Two tokens mapping to the *same* identity share pages exactly as one token does — the identity is what owns a page, so it is the identity that has to differ. Members of the *General public* get this for free: `POST /public-sessions` mints a token with an identity of its own each time (see [Public access](public-access.md)).


## Musicorpus Page

This is the heart of the API, where a *User* may upload page scans, start *Pipeline Executions* and download generated files.

Working with *Musicorpus Pages*:

- `POST /musicorpus-pages` Creates a new and empty *MusicorpusPage*, returns that page's representation, including its ID (a 12-character NanoID — random and URL-safe, not sequential, so pages cannot be enumerated across users).
- `GET /musicorpus-pages/{id}` Fetches information about a given *MusicorpusPage*
- `DELETE /musicorpus-pages/{id}` Deletes a *MusicorpusPage* and frees all of its resources (including killing any running *Pipeline Executions*).

Working with *Files*:

- `GET /musicorpus-pages/{id}/files` Lists the *Files* the page currently holds — each with its path, size in bytes and last-modified time. Paths are the ones the [Musicorpus Specification](https://github.com/OmniOMR/musicorpus/blob/main/docs/musicorpus-specification/musicorpus-specification.md) and the *Signature* use (`image.jpg`, `Staves/3/image.jpg`), so a path from here can be handed straight to `file-urls` or named as an execution's `input`.

This is the only way to learn what a *PipelineExecution* produced: how many staves a page has is what the recognition found out, so the output *File* set is not knowable in advance. It is answered by listing object storage rather than from anything the service remembers — the service is not in the byte-path and keeps no list of its own — which also makes it true across a *File* that a later execution overwrote. The order is storage's own, lexicographic by key, which puts `Staves/10/` before `Staves/2/`.

It is also how a running execution is watched from the outside: poll it while an execution runs and *Files* appear as they are written — or, better, keep [the file-change stream](#the-file-change-stream) open and list the page when it says something has been written. What the execution is *saying* while it does that is [the log stream](#the-log-stream).

```
GET /musicorpus-pages/{id}/files

200 OK
{
  "files": [
    { "path": "Staves/1/image.jpg", "size": 40213, "last_modified": "2026-07-22T16:03:11Z" },
    { "path": "image.jpg", "size": 918273, "last_modified": "2026-07-22T16:01:52Z" },
    { "path": "layout.json", "size": 2143, "last_modified": "2026-07-22T16:03:09Z" }
  ]
}
```

A *File* is not attributed to the execution that wrote it. A page's folder is flat storage that any number of executions have written into, and a later one may overwrite what an earlier one produced, so the attribution would be a guess that goes stale; a caller wanting the connection reads it from the executions' *Signatures*.

- `POST /musicorpus-pages/{id}/file-urls` Issues short-lived, presigned MinIO URLs for uploading and/or downloading *Files* directly to and from object storage — this keeps the non-scaling `api` service out of the file byte-path. The request body lists the *Files* to upload (`put`) and/or download (`get`); the response maps each path to a presigned URL plus an expiry. The client then transfers the bytes straight to/from MinIO.

```
POST /musicorpus-pages/{id}/file-urls
{ "put": ["image.jpg"], "get": ["transcription.musicxml"] }

200 OK
{
  "put": { "image.jpg": "https://<minio-public>/bucket/{id}/image.jpg?X-Amz-Signature=..." },
  "get": { "transcription.musicxml": "https://<minio-public>/bucket/{id}/transcription.musicxml?X-Amz-Signature=..." },
  "expires_at": "2026-07-22T16:05:00Z"
}
```

Executing *Pipelines*:

- `POST /musicorpus-pages/{id}/pipeline-executions` Starts a new pipeline execution, with its name and version specified in the payload, alongside an `input` array naming the *Files* of the page to process. Returns that pipeline's representation, including its ID (integer, autoincrementing per page).

`input` is required and has no default: this service keeps no list of a page's *Files*, and uploads travel over presigned URLs, so it knows which it minted and never which were used. It is checked against the *Pipeline's* announced *Signature* and a list that does not fit is a `400` — see [Signatures](signatures.md).
- `GET /musicorpus-pages/{id}/pipeline-executions` Returns the list of completed and running pipeline executions for this page.
- `GET /musicorpus-pages/{id}/pipeline-executions/{id}` Returns information about a specific pipeline execution.


## Pipelines

Endpoints to inspect available *Pipelines* and their versions.

- `GET /pipelines` Returns the list of known and available *Pipelines* and their versions and *Orchestrators* they can run on.
- `GET /pipelines/{pipeline-name}` Returns the list of versions of a given *Pipeline*, used by users to check when a newer version becomes available.

This listing is not configured anywhere — it is assembled from what *Orchestrators* and *Workers* announce over RabbitMQ, and it includes an *ImplicitPipeline* for every known *Model*. Beside the `pipelines` array, the response carries a top-level `warnings` array reporting name and signature conflicts between announcing providers. See [Discovery](discovery.md) for the response shape and for why the listing may lag reality by a few seconds.


## The log stream

- `POST /musicorpus-pages/{id}/logs` Opens a [Server-Sent Events](https://developer.mozilla.org/en-US/docs/Web/API/Server-sent_events) stream of everything logged for this page: what each *Model* and *Pipeline* printed, and the `api` service's own account of each *Pipeline Execution*.

One stream per *MusicorpusPage* rather than per *Pipeline Execution*. A page may be read several times, and somebody debugging a reading wants the whole story in the order it happened rather than two of them to interleave by hand; every event names the execution it belongs to.

```
POST /musicorpus-pages/{id}/logs

200 OK
Content-Type: text/event-stream

data: {"execution_id": 1, "seconds": 0.0, "kind": "api", "source": "api", "level": "info", "message": "running staff-detector 2026-07-22 on image.jpg"}

data: {"execution_id": 1, "seconds": 1.3, "kind": "worker", "source": "staff-detector", "level": "info", "message": "7 staves"}

: ping

data: {"execution_id": 1, "seconds": 2.1, "kind": "api", "source": "api", "level": "info", "message": "completed in 2.1s"}
```

`seconds` is time since that execution started, not a timestamp: what a reader is judging is how long a step took rather than what time of day it was. It is measured on the `api` service's clock — the one clock every line passes through — since a *Worker* on another machine may disagree by seconds. `kind` is `worker` or `orchestrator` for a line something printed, and `api` for the service saying what it did with the execution; `level` is `debug`, `info`, `warning` or `error`, and a *Model's* stderr arrives as `warning`. Comment frames (`: ping`) keep an idle connection open and mean nothing.

The stream ends when the client hangs up or when the page is deleted. It does not end when an execution finishes — the next one on the same page arrives on the same stream.

**Nothing is replayed.** The service holds no buffer, so lines produced while nobody was watching are gone, and a client that wants a whole execution's log opens the stream before starting the execution. A log here is a *User* watching a page being read, not a record kept for later; the outcome of an execution is in the execution itself, and what it produced is in the file listing.

It is a `POST`, unusually for something that reads. A `GET` invites `EventSource`, which cannot send an `Authorization` header — and the usual way round that is to put the token in the query string, where it lands in proxy logs and browser history. Every request to this API authenticates the same way, so the endpoint is one a browser reads with `fetch`.


## The file-change stream

- `POST /musicorpus-pages/{id}/file-changes` Opens an SSE stream naming the *Files* this page's executions write, as they are written.

```
POST /musicorpus-pages/{id}/file-changes

200 OK
Content-Type: text/event-stream

data: {"execution_id": 1, "paths": ["layout.json"]}

: ping

data: {"execution_id": 2, "paths": ["Staves/1/transcription.musicxml", "Staves/1/transcription.lmx"]}
```

A notice is an **invitation to look, not a description of the page**. It names paths and nothing else; what the page holds — each *File* with its size and modification time — is `GET /musicorpus-pages/{id}/files`, answered from object storage. A client reads a notice as "listing the page again is worth it now", which is what makes a *File* appear as it is written rather than at the next poll.

That the paths are attributed to an execution here does not contradict the listing's refusal to attribute a *File* to one. A notice is an **event** and says who wrote it *then*; the listing is a **state**, and a later execution may have overwritten it since.

Paths are those created and those overwritten, which are not told apart — the *Worker Head* detects that a *File* changed, not how. Deletions never appear at all: they do not propagate out of a *Model* (see [Rough edges](rough-edges.md)), so an absence from this stream means nothing.

Nothing is replayed and nothing is acknowledged, so a client that misses a notice loses latency and nothing else. Notices **coalesce** while a client is not reading: two writes of one path between reads arrive as one event naming it once, since the answer to any number of them is the same single listing.

This is a stream of its own rather than a second event type on the log stream. A log is text for a human and there is a great deal of it — for a deep-learning model, mostly its libraries' warnings — and a client that only wants to know about a new *File* should not have to read all of it to find out. Like the log stream it is a `POST`, for the same reason.


## The result stream

- `POST /pipeline-execution-results` Opens an SSE stream of every *Pipeline Execution* of yours that ends, as it ends.

```
POST /pipeline-execution-results

200 OK
Content-Type: text/event-stream

data: {"page_id": "7Kf2mP9xLwQa", "execution": {"execution_id": 1, "pipeline_name": "hello-world", "pipeline_version": "1.0.0", "input": ["image.jpg"], "state": "completed", "error": null}}

: ping

data: {"page_id": "Qm3vN8xTrb2c", "execution": {"execution_id": 1, "pipeline_name": "hello-world", "pipeline_version": "1.0.0", "input": ["image.jpg"], "state": "failed", "error": "No staves found in the image."}}
```

The one stream scoped to a **User** rather than to a page, because that is who wants it: a client holding twenty pages in flight wants one connection telling it which have finished, not twenty. A client watching a single page filters on `page_id`, which costs it nothing. `execution` is the same shape `GET /musicorpus-pages/{id}/pipeline-executions/{id}` answers with, already in its final state — a *result* is by definition an ending, so `running` never appears here. A timeout is an ending too, and is announced like any other.

**It carries every page of your identity**, including pages created by somebody else holding the same token. Musibot has no sessions (see [Authentication](#there-are-no-sessions-only-identities)), so a client watches for the page IDs it created and ignores the rest — which it can, since no endpoint answers "all my pages" and a client is already obliged to track its own. Where a real separation is wanted, use two identities.

Nothing is replayed here either, so a client **reconciles on connect**: an execution that ended before the stream opened, or while it was broken, is not announced afterwards, and the way to learn about it is to ask. Treat this as the thing that saves you from polling rather than as the only way you can learn. A watcher that falls a thousand results behind is disconnected rather than quietly missing one — losing a result silently would leave a client waiting on a page for ever, with no way to notice.

> **Note:** There is no progress reporting anywhere in Musibot, and none is planned. A *Model* execution takes a second or two, and the models Musibot runs cannot say how far along they are — a detector produces every box at the end of one forward pass, and an autoregressive model does not know how many tokens it is about to emit. What a *User* watching gets is these two streams: the log, and a *File* listing that grows as *Files* are written.
