# Changelog for `python-client`

Released as `python-client/vX.Y.Z` git tags — see [Versioning and releases](../../docs/versioning-and-releases.md). The distribution is named `musibot-client`.

Versions are semver, independent of the `api` service's release cadence. This is a public, outward-facing contract, so entries are written for the people calling it.


## Unreleased


## 0.3.0 — 2026-08-14

Collections rather than pages, and nothing polls any more. Needs an `api` service of 0.3.0 or newer, which serves the stream `wait_for_execution` now waits on.


### Added

- **`process_pages`: a whole collection, not a loop.** Hand it an iterable of `BatchJob`s and it keeps several pages in flight, yielding a `BatchResult` as each finishes. Built for the two workloads that asked for it — a library running its collection through, and a benchmark rig measuring a *Pipeline* over a dataset on disk — so the shape follows from those: results carry the `key` you gave the job, they arrive as pages finish rather than in order, and **a failed page is a result rather than an exception**, because one unreadable scan among a million is not a reason to stop. Jobs are pulled lazily, one page at a time as a worker frees up, so a generator that fetches each scan never has more than `concurrency` of them in memory. Stopping early deletes the pages still in flight.

- **Retries for trouble that is not the page's fault.** A connection that dropped, a service restarting behind a proxy, a `429` — each is retried with a doubling backoff and a warning in the log, so a run that met a ten-minute outage overnight is finished by morning rather than 98% finished. Configured with `RetryPolicy`, which `process_page` takes too; `RetryPolicy.none()` turns it off. A *Pipeline* that ran and failed is never retried — the *Model* answered — and neither is a `4xx` that is a statement about the request.

- **`watch_execution_results()`** — the raw stream of every ending of this token's identity. It carries pages another script sharing the token created, since Musibot has no sessions, so filter on `page_id` for your own.

- **`output` may be a predicate**, on `process_page` as well as on `process_pages`: `output=lambda file: file.path.endswith(".musicxml")` asks the page what it holds and takes what matches, which is how outputs are collected when the recognition decides how many there are.

- **A reference page.** [Every method, model and error](../../docs/python-client-reference.md), and the batch guide the docs promised as a TODO.

### Changed

- **Nothing polls any more.** `wait_for_execution` used to ask the server every second whether an execution had finished; it now waits on one stream of endings that the client holds open for all of its pages, so twenty pages in flight cost one connection instead of twenty pollers. It still asks about its execution once as it starts waiting, because nothing on that stream is replayed and an execution may have ended already, and it reconciles the same way whenever the connection drops and comes back.

  Two consequences worth knowing. `poll_interval_seconds` is gone from the constructor — there is nothing to pace. And `process_page` now retries by default, where before it reported the first infrastructure failure it met; pass `retry=RetryPolicy.none()` for the old behaviour.

  This needs an `api` service serving `POST /pipeline-execution-results` (0.3.0 or newer).


## 0.2.0 — 2026-08-07

A page's *Files* can be listed, which is how the output of a *Pipeline* nobody could predict the shape of is discovered. `start_execution` now names its input explicitly; `process_page` is unchanged for the caller.


### Added

- **`list_files`** — the *Files* a page currently holds, as `PageFile` objects carrying `path`, `size` and `last_modified`. What a *Pipeline* produced is not knowable in advance (a page-level run writes a `Staves/{n}/` folder whose size depends on the page), so this is how outputs are discovered before `download_files` is called with their paths. It can also be polled while an execution runs to watch *Files* appear.


### Changed

- **`start_execution` takes an `input` list** naming the *Files* to process. It is explicit because the server cannot supply it — it keeps no list of a page's *Files* and never learns which presigned upload URLs were used. A caller holding one page open across several executions names the *Files* for each of them.
- **`process_page` fills it in** from the dict it just uploaded, so the common round trip is unchanged.
- **`PipelineExecution` carries `input`.**


## 0.1.0 — 2026-07-27

First prototype release: the whole round trip in one call. Everything below is new.


### Added

- **`MusibotClient`** — configured with a Musibot API URL and an API token, usable as a context manager and closable.
- **`process_page`** — the whole round trip in one call: create a page, upload the input *Files*, start the *Pipeline Execution*, wait for it, download what was asked for, delete the page. The page is deleted even when the execution fails, since a failure is no reason to leave one behind on the server. See [Using the python client](../../docs/using-python-client.md).
- **Every step as a method of its own** — `create_page`, `get_page`, `delete_page`, `file_urls`, `upload_files`, `download_files`, `start_execution`, `get_execution`, `list_executions`, `wait_for_execution` — for callers who want to hold a page open across several executions or watch progress themselves.
- **`list_pipelines`** — what is currently available on the server, *ImplicitPipelines* included.
- **Direct transfers to object storage.** *File* bytes never pass through the `api` service: it issues short-lived presigned URLs and this client transfers straight to and from storage, which is what keeps the one non-scaling service out of the byte path.
- **Typed errors** — `MusibotError` as the base, with `MusibotApiError` when the server refuses a request, `PipelineNotAvailable` when no *Worker* or *Orchestrator* provides the requested *Pipeline*, `PipelineExecutionFailed` when it ran and failed, and `PipelineExecutionTimedOut` when the client gave up waiting.


### Not yet implemented

- **Progress streaming.** `wait_for_execution` polls once a second; the SSE stream that will replace it does not exist on the server side yet either.
- **Batch helpers.** The library-scale burst workflow described in the docs is still a TODO.


### Notes

- Requires **python 3.11+**. Dependencies are kept light — `core` and `httpx` — because this installs on end-user machines alongside whatever else they have.
- Not published to PyPI yet; install it from a git link while Musibot is on `0.x` and used only internally. See [Versioning and releases](../../docs/versioning-and-releases.md).
