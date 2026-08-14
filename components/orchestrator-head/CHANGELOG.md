# Changelog for `orchestrator-head`

Released as `orchestrator-head/vX.Y.Z` git tags — see [Versioning and releases](../../docs/versioning-and-releases.md).

Versions are semver on the **interface a *Pipeline* is written against**: the `Pipeline` class, the `PipelineContext` it is handed, and the testing helpers. That is the contract custom *Orchestrators* build on, and it is what a breaking change here breaks. Entries are written for whoever writes *Pipelines*.


## Unreleased

First implementation. Everything below is new.


### Added

- **A *Pipeline* is a class** (`Pipeline`) that sets `name`, `version` and `signature` and implements one `async execute(ctx)`. An *Orchestrator* registers instances of it, so the same implementation may be registered twice under two names with different constructor arguments — one pinning a stable *Model* version, one pinning the version being developed — without any of its code being copied. Those constructor arguments are *registration parameters*, and they are not the same thing as the *execution parameters* a *User* sends with one request, which arrive as `ctx.parameters`.

- **`PipelineContext`** — everything a *Pipeline* may do to the rest of Musibot:

  | | |
  | --- | --- |
  | `ctx.page_id`, `ctx.execution_id` | which execution this is |
  | `ctx.input` | the *Files* the *User* named, already checked against the *Signature* |
  | `ctx.parameters` | what the *User* sent with this execution |
  | `ctx.logger.info(...)` | a line for whoever is watching the page, `%`-style arguments and all |
  | `await ctx.read_bytes/read_text` | one *File* out of the page |
  | `await ctx.write_bytes/write_text` | one *File* into the page, announced as it lands |
  | `await ctx.list_files/exists` | what the page holds |
  | `await ctx.execute_model(model, input=[...])` | run one *Model* and wait for it |

  The file methods are named after `pathlib`'s. They are coroutines because each one reaches object storage; `ctx.logger` is not, because a log line is fire-and-forget and awaiting one would buy nothing.

- **Files are fetched from object storage per use**, not mirrored locally the way a *Worker Head* mirrors them for its *Model*. A *Pipeline* runs for as long as everything it invokes put together, and the *Models* it invokes write into the same page while it runs — so a mirror taken at the start would be stale by the middle. A *Pipeline* that wants the current bytes reads them.

- **`ctx.execute_model` pins a *Model* by name and version, exactly.** There is no loose version selection and none is planned: exact pinning is what makes a *Pipeline* reproducible, and a *Pipeline* that wants to follow a moving *Model* takes the version as a registration parameter. A *Model* that fails raises `ModelExecutionFailed`; several run concurrently under an ordinary `asyncio.TaskGroup`.

- **`musibot.orchestrator_head.testing`** — `PipelineRunner` runs a *Pipeline* against an in-memory *MusicorpusPage* with no broker, no object storage and no *Models*, and afterwards tells you what the *Pipeline* read, wrote, logged and invoked. Fake *Models* are behaviours you register, which may write into the page as a real one would, or raise to exercise the failure path. `run` is synchronous so that testing a *Pipeline* needs no async test framework; `run_async` is there for a test already on an event loop. It also applies the same input-list check the `api` service does, so a test cannot hand a *Pipeline* a list a *User* could never send.

- **`OrchestratorHeadSettings`** — the shared RabbitMQ, MinIO and logging blocks from `core`, plus `max_concurrent_executions` (default 4). An *Orchestrator* subclasses it to give its *Pipelines* their registration parameters, and gets command line arguments, environment variables and config-file keys for them for free. Nothing is required: against the [local development stack](../../deploy/README.md) an *Orchestrator* takes no arguments at all.


### Notes

- Requires **python 3.11+**, the floor `core` sets — and unlike a *Model*, a *Pipeline* has no way around it: it runs inside this process.
- Depends on `core`, `boto3` and `aio-pika`. Deliberately not kept as thin as the worker head's: an *Orchestrator* runs in this process and is coupled to Musibot's domain by design.
- There is no console script. An *Orchestrator Head* is never started on its own — the *Orchestrator* is the program.
