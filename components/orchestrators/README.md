# orchestrators

Some *Orchestrators* ship inside this monorepo (this folder) and others live in their own repositories, depending on this repo only through the `orchestrator-head` interface. An *Orchestrator* is a set of *Pipeline* implementations, run by an `orchestrator-head`.


## What an orchestrator provides

A set of *Pipelines* — `async` python functions that read and write *MusicorpusPage* *Files* and invoke *Models*. Unlike a *Model* (isolated behind a subprocess), an *Orchestrator* is tightly coupled to Musibot: it imports `orchestrator-head` and `core` and runs in-process with them.


## Layout (per reference orchestrator in this folder)

```
orchestrators/<orchestrator-name>/
  pyproject.toml         # deps for THIS orchestrator's pipelines
  <orchestrator-name>/   # pipeline implementations
  tests/
  README.md
```


## Runtime

A single process on the same python version as the other core services, but with its own venv — its *Pipelines* may pull in extra dependencies (e.g. OpenCV) that could otherwise conflict. It needs no special hardware or per-model runtime, unlike a *Model*.


## Deployment

Install the orchestrator together with `orchestrator-head` into a venv and start it against RabbitMQ + MinIO (see `docs/deployment.md`). A new or in-development orchestrator can be plugged into a running system just by connecting to RabbitMQ.


## Testing

Per-orchestrator unit tests for pipeline logic, plus integration tests exercising a full pipeline against fake models.


## Versioning

A *Pipeline* is identified by name and version; an orchestrator bundles a set of them.
