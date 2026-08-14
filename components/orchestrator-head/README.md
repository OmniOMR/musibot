# orchestrator-head

The Musibot-provided interface layer that a single *Orchestrator* runs inside. It is the counterpart to `worker-head` on the model side, but with the opposite coupling: where a worker head runs its *Model* as an isolated subprocess, an orchestrator head runs its *Orchestrator* **in the same process** — pipeline code is tightly coupled to Musibot's domain (it reads *MusicorpusPage* *Files*, invokes *Models*, and speaks the RabbitMQ and MinIO protocols), so isolating it would only get in the way.

[Writing pipelines](../../docs/writing-pipelines.md) is the guide to using this. This page is what the component *is*.


## What an Orchestrator looks like

```py
from musibot.orchestrator_head import (
    NameAndVersion,
    Orchestrator,
    Pipeline,
    PipelineContext,
    Signature,
)


class HelloPipeline(Pipeline):
    signature = Signature(input=["image.jpg"], output=["layout.json"])

    def __init__(self, name: str, version: str, *, model: NameAndVersion):
        self.name, self.version, self._model = name, version, model

    async def execute(self, ctx: PipelineContext) -> None:
        await ctx.execute_model(self._model, input=["image.jpg"])
        ctx.logger.info("the model has run")


def main() -> None:
    settings = MyOrchestratorSettings.load()

    orchestrator = Orchestrator("my-orchestrator", settings)
    orchestrator.register_pipeline(
        HelloPipeline(
            "hello-pipeline", "1.0.0", model=NameAndVersion(name="hello-model", version="1.0.0")
        )
    )
    orchestrator.run()
```

A *Pipeline* is a **class**, and an *Orchestrator* registers **instances** of it. That is what lets one implementation be registered twice under two names — `mzk` pinning the *Model* version in production and `mzk-dev` pinning the one being developed — with no code copied between them. The settings are loaded before the *Pipelines* are constructed, which is what lets a command line argument reach a constructor.


## Two kinds of parameter

The word means two different things here, and they arrive by different routes:

| | Comes from | Reaches the *Pipeline* as | Changes |
| --- | --- | --- | --- |
| **Registration parameters** | the *Orchestrator's* own configuration | constructor arguments | never, for the life of the process |
| **Execution parameters** | the *User*, on one request | `ctx.parameters` | every execution |


## What a Pipeline can do

`PipelineContext` is the whole surface. `ctx.page_id`, `ctx.execution_id`, `ctx.input` and `ctx.parameters` say what this execution is; `ctx.logger` says what is happening; `read_bytes`, `read_text`, `write_bytes`, `write_text`, `list_files` and `exists` reach the page's *Files*; and `execute_model` runs a *Model*.

Two shapes of that are worth naming:

- **Files are fetched per use, not mirrored.** A *Worker Head* stages a local copy of a page because its *Model* knows nothing of MinIO. A *Pipeline* is python in this process, so it reads what it asks for when it asks for it. It never holds a stale copy of a *File* that a *Model* rewrote while it ran, and it never moves bytes it does not care about.
- **`ctx.logger` is not a coroutine, and the file methods are.** A log line is fire-and-forget, so awaiting one would buy nothing; a file read is a network call, so it cannot pretend otherwise.

`execute_model` pins a *Model* by name **and version, exactly** — that is what makes a *Pipeline* reproducible. Several run concurrently under an ordinary `asyncio.TaskGroup`, which is the shape a page-level pipeline has: one *Model* execution per staff.


## What one Pipeline Execution looks like

1. A `pipeline-execution-start` arrives on the shared queue for one *Pipeline's* name and version. The head waits for a free execution slot, then acknowledges — **the instant the execution begins, never when it ends**, so an *Orchestrator* that dies mid-execution does not have its work redelivered and every *Model* in it run a second time. Until then the message stays unacknowledged and another instance is free to take it.
2. The *Pipeline's* `execute` runs, under the deadline the request carried.
3. Whatever it invokes goes out as `model-execution-start` naming this head's own reply queue, and the answers come back there. Each carries the *remaining* time, so nothing this head dispatches outlives the execution that asked for it.
4. Whatever it logs and whatever *Files* it writes are published as they happen, straight to the `api` service.
5. The outcome is published as `pipeline-execution-result`. A *Pipeline* that raises is a failed execution whose error message is the exception's, so that message is worth writing for a human.

A `pipeline-execution-terminate` cancels a running execution and publishes no result — whoever asked for the termination has already settled it.


## Testing a Pipeline

`musibot.orchestrator_head.testing.PipelineRunner` runs a *Pipeline* against an in-memory page with no broker, no object storage and no *Models*, and then tells you what it read, wrote, logged and invoked. It is part of what this component offers rather than a convenience for its own test suite — a *Pipeline* is ordinary python and should be testable the way ordinary python is.

```py
runner = PipelineRunner({"image.jpg": JPEG})
runner.register_model(
    HELLO_MODEL, lambda call, files: files.update({"transcription.musicxml": b"<score/>"})
)

runner.run(HelloPipeline("hello-pipeline", "1.0.0", model=HELLO_MODEL), input=["image.jpg"])

assert "layout.json" in runner.files
```

`run` is synchronous, so testing a *Pipeline* needs no async test framework; `run_async` is there for a test already on an event loop. A fake *Model* may write into the page exactly as a real one would, or raise to exercise the failure path. The runner also applies the same input-list check the `api` service does, so a test cannot hand a *Pipeline* a list a *User* could never send.


## Depends on

`core` (the domain model and wire protocol), `boto3` and `aio-pika`. Unlike the worker head — which is kept deliberately thin because it is installed into a *Model's* environment — this is meant to be coupled to Musibot's domain.

Its `Broker` is the third hand-written one in this repository, which is deliberate; `components/core/README.md` says what that buys and names the trigger that would end it. The queue declarations the three must agree about come from `core`.


## Configuration

Beyond the shared RabbitMQ, MinIO and logging blocks (see [service configuration](../../docs/service-configuration.md)):

| Setting | Meaning |
| --- | --- |
| `max_concurrent_executions` | How many *Pipeline Executions* this process runs at once. Default 4. |

Nothing is required. Against the [local development stack](../../deploy/README.md) an *Orchestrator* starts with no arguments at all. An *Orchestrator* that needs settings of its own subclasses `OrchestratorHeadSettings` and gets command line arguments, environment variables and config-file keys for them for free.


## Development

```bash
cd components/orchestrator-head
python3 -m venv .venv
.venv/bin/pip install -e ../core -e '.[dev]'
```

Exercised end to end by [hello-orchestrator](../orchestrators/hello-orchestrator/README.md), which needs the [local development stack](../../deploy/README.md), a *Worker* running [hello-model](../models/hello-model/README.md), and the `api` service.


## Testing

RabbitMQ and object storage are faked — those are what a test cannot reasonably run — and everything else is real, the *Pipeline* code and the concurrency around it included. The storage tests run against the local stack's MinIO and skip themselves when it is not up.

```bash
.venv/bin/python -m pytest
.venv/bin/python -m ruff check .
.venv/bin/python -m ruff format --check .
.venv/bin/python -m mypy
```


## Not yet implemented

- **Musicorpus helpers.** Slicing a page into staff images and concatenating staff MusicXML into a page-level file are things every real *Pipeline* will want, and neither is here. They belong in a library of their own rather than in this head, which knows only that a *File* is bytes.


## Deployment

`pip install`ed into an *Orchestrator's* virtual environment and started with RabbitMQ and MinIO credentials (see [deployment](../../docs/deployment.md)). It is never deployed on its own — it always hosts exactly one *Orchestrator*, and there is no console script here because the *Orchestrator* is the program.


## Versioning

Semver on **the interface a *Pipeline* is written against** — the `Pipeline` class, the `PipelineContext` it is handed, and the testing helpers. That is the contract custom *Orchestrators* build on, including ones in their own repositories. The version is derived from the `orchestrator-head/v*` git tags rather than written into `pyproject.toml`; see [Versioning and releases](../../docs/versioning-and-releases.md) and [CHANGELOG.md](CHANGELOG.md).
