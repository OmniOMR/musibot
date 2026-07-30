# Changelog for `worker-head`

Released as `worker-head/vX.Y.Z` git tags — see [Versioning and releases](../../docs/versioning-and-releases.md).

Versions are semver on the **IPC contract** between the worker head and a *Model*, which is the interface to keep stable — a model records the worker-head version it targets. Entries are written for whoever installs this alongside a model.


## Unreleased


### Added

- **A *Model* that reported success without writing an output its *Signature* promises now fails the execution.** Only the slot-free, non-optional entries are checked — how many *Files* fill a `Staves/{*}/image.jpg` is the *Model's* to decide. Writing output to the wrong path is the commonest way to get a *Model* wrong, and it otherwise shows up as a *Pipeline* that succeeds and produces nothing.
- **Files the *Model* wrote that its *Signature* does not describe are logged**, and still uploaded — filtering them away would silently swallow a diagnostic file somebody meant to keep.


## 0.1.0 — 2026-07-27

First prototype release: a worker head that runs one *Model* and connects it to Musibot. Everything below is new.


### Added

- **Model execution loop** — consumes `model-execution-start` messages from the shared queue for one model's name and version, and publishes the result to the queue named by the request's `reply_to`. Who that reply goes to — an *Orchestrator Head*, or the `api` service running an *ImplicitPipeline* — is not this head's business.
- **Immediate acknowledgement.** Work is acked as it is taken, not when it completes: a *Worker* that dies mid-execution must not have the work redelivered and the model run twice. The execution instead times out from the `api` service's point of view.
- **Model subprocess over IPC** — the model runs as a child process driven over a dedicated pair of pipes plus the filesystem, leaving its own stdout and stderr free to be captured as its log. Nothing is shared with the model's environment except this contract, so a model may bring its own python version and its own dependencies. See [Worker IPC](../../docs/worker-ipc.md).
- **Speaks worker IPC version 1**, and refuses to run a *Model* that announces any other. That integer versions the protocol and is not this component's semver — the two move independently, and it is the one a *Model* is actually checked against. See [the protocol version](../../docs/worker-ipc.md#the-protocol-version).
- **Page staging against MinIO** — the *Files* a request declares as input are downloaded into a local mirror of the bucket, one folder per *MusicorpusPage*; whatever the model created or changed is uploaded afterwards and the mirror discarded. It is scratch space for one execution, not a cache.
- **Discovery** — announcement on startup, periodic heartbeats, replies to discovery probes, and a goodbye on shutdown, so the `api` service knows what this worker offers. Handles terminate requests. See [Discovery](../../docs/discovery.md).
- **Configuration** — beyond the shared RabbitMQ, MinIO and logging blocks: `model_command` (required — the command that launches the model), `pages_dir` (a temporary directory when unset, the normal case) and `model_ready_timeout_seconds`, which is generous by default because that is where a model loads its weights.


### Not yet implemented

- **Batching.** A model's `supports_batching` is read and announced, but every execution is sent as its own `execute` command and no `execute-batch` is ever issued. A batching model therefore works correctly, just without the throughput it could have.
- **Log and progress forwarding.** A model's stdout and stderr are captured and drained — which they must be, or the model blocks on its next `print` — but they go to this head's own log rather than onto `musibot.logs` for the `api` service to stream. Same for `progress` messages.


### Notes

- Requires **python 3.11+**, the floor `core` sets. That environment may be the model's own virtual environment, and usually is; a model that cannot live there — pinned to an older python, or with conflicting dependencies — gets a venv of its own and is launched by absolute path across the IPC boundary.
- Dependencies are kept deliberately thin (`core`, `boto3`, `aio-pika`) because every one of them is a dependency that could conflict with a model's.


### Known rough edges

File-change detection compares size and modification time against a pre-run snapshot, so deletions do not propagate and a file rewritten to the same size within one clock tick would be missed; and there is no per-model timeout, so a hung model ties up the worker for the whole pipeline budget. See [Rough edges](../../docs/rough-edges.md).
