# Changelog for `worker-head`

Released as `worker-head/vX.Y.Z` git tags — see [Versioning and releases](../../docs/versioning-and-releases.md).

Versions are semver on the **IPC contract** between the worker head and a *Model*, which is the interface to keep stable — a model records the worker-head version it targets. Entries are written for whoever installs this alongside a model.


## Unreleased


### Added

- **A *Model's* output now reaches the *User*.** Every line the model prints on stdout or stderr is published on the `musibot.logs` exchange as it is read — stdout at level `info`, stderr at `warning` — attributed to the *Pipeline Execution* that caused the work, and the `api` service streams it to whoever is watching that page. This is what the IPC's two dedicated file descriptors were always for: a *Model* needs no logging setup, and `print("staff 3/12")` is the whole of the obligation. Nothing in the IPC contract changes, so a *Model* written against 0.2.1 needs nothing done to it. Two lines of the head's own go out beside them: what the model wrote, and, when an execution fails, why — the latter because the result travels to whoever asked while the log travels to the *User*, and an *Orchestrator* is free to report a failure of its own and lose the model's reason on the way.

- **A *Worker* announces the *Files* it wrote.** After uploading a *Model's* output it publishes a `files-changed` notice on `musibot.file-changes` naming those paths, attributed to the *Pipeline Execution* that caused them, so a client watching that page can show a *File* as it appears instead of at its next poll. Published after the upload and never before — a client told about a *File* that has not reached storage yet would fetch a `404` — and fire-and-forget, like the log: object storage is the truth about what a page holds, so a broker that refuses a notice costs latency rather than work. Nothing in the IPC contract changes.

### Removed

- **`progress` is no longer a message of the IPC.** A *Model* sending one is now ignored exactly as any other unknown message type is, so nothing breaks, and the `ProgressMessage` it was forwarded as is gone from `core`. Progress reporting is not coming back: an execution takes a second or two, and the models Musibot runs cannot say how far along they are — a detector produces every box at the end of one forward pass, and an autoregressive model does not know how many tokens it is about to emit.


## 0.2.1 — 2026-08-07

A packaging fault that stopped 0.2.0 starting anywhere it was actually deployed. The IPC contract and the head's behaviour are unchanged, so a *Model* written against 0.2.0 needs nothing done to it.


### Fixed

- **A *Worker* starts in a virtual environment that has only its runtime dependencies.** `storage.py` imported `S3Client` from `mypy_boto3_s3` at module scope — that package is `boto3-stubs[s3]`, which is declared under `dev` and is not installed beside a deployed worker. So the head crash-looped on `ModuleNotFoundError` before it had started its *Model*, and it did so *only* in production: every development environment has the stubs, and nothing local ever noticed. The import now sits under `TYPE_CHECKING`. This is the same fault as the `api` service's, in the copy of this module that lives here.


## 0.2.0 — 2026-08-07

Honours the deployment's key prefix, fails a *Model* that reported success without writing what its *Signature* promised, and stops cleanly when a terminal sends Ctrl+C. The IPC contract itself is unchanged — a *Model* written against 0.1.0 needs nothing done to it.


### Changed

- **Object keys are built through `core`'s `ObjectLayout`**, so a worker head honours the deployment's `s3_key_prefix` when staging a *Model's* inputs and uploading what it produced. A head configured with a different prefix from the `api` service stages nothing and uploads where nobody looks, and neither half raises — so the prefix belongs in the same configuration file as the rest of the MinIO connection. Nothing changes for a deployment that leaves it empty. See [Service configuration](../../docs/service-configuration.md).


### Fixed

- **Ctrl+C no longer looks like a model crash.** The *Model* is now started in a session of its own, so a terminal's `SIGINT` — which the kernel delivers to the whole foreground process group — reaches the head and not the model. The head then stops its model deliberately, over the protocol, exactly as it does when signalled on its own. Before this, a head started from a shell and stopped with Ctrl+C logged `The model exited unexpectedly with code -2` and failed whatever was in flight, because the model was killed before the head had asked it to stop.
- **Stopping a *Model* signals its process group**, so workers a model started itself are not left behind when it has to be terminated. A model that exits politely on `shutdown` is still responsible for its own children.


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
