# orchestrators

Some *Orchestrators* ship inside this monorepo (this folder) and others live in their own repositories, depending on this repo only through the `orchestrator-head` interface. An *Orchestrator* is a set of *Pipeline* implementations, run by an `orchestrator-head`.


## What an orchestrator provides

A set of *Pipelines* — subclasses of `Pipeline` that read and write *MusicorpusPage* *Files* and invoke *Models*, registered as **instances**, so one implementation can be registered twice with different parameters. Unlike a *Model* (isolated behind a subprocess), an *Orchestrator* is tightly coupled to Musibot: it imports `orchestrator-head` and `core` and runs in-process with them. See [Writing pipelines](../../docs/writing-pipelines.md).


## In this folder

- [omniomr-orchestrator](omniomr-orchestrator/) — the OmniOMR project's *Pipelines*, and the reason Musibot exists. Its `mzk` pipeline reads a page scan into a page-level MusicXML file: staff detection, slicing, a transcription per staff, and one score.
- [hello-orchestrator](hello-orchestrator/) — recognises nothing, and exercises everything: it runs a *Model*, reads what that *Model* wrote, and writes a *File* of its own. The worked example to read first, and the counterpart of `hello-model`.


## Layout (per orchestrator in this folder)

```
orchestrators/<orchestrator-name>/
  pyproject.toml         # deps for THIS orchestrator's pipelines
  <orchestrator_name>/   # pipeline implementations, and the startup script
  tests/
  README.md
```


## Runtime

A single process on the same python version as the other core services, but with its own venv — its *Pipelines* may pull in extra dependencies (e.g. OpenCV) that could otherwise conflict. It needs no special hardware or per-model runtime, unlike a *Model*.


## Deployment

Install the orchestrator together with `orchestrator-head` into a venv and start it against RabbitMQ + MinIO (see `docs/deployment.md`). A new or in-development orchestrator can be plugged into a running system just by connecting to RabbitMQ.


## Testing

Per-orchestrator unit tests for pipeline logic, using `PipelineRunner` from the head's `testing` module: it runs a *Pipeline* against an in-memory page with no broker, no object storage and no *Models*, so a test needs none of Musibot running and no async test framework.


## Versioning

A *Pipeline* is identified by name and version, and both are declared in its code — the same rule as a *Model's*, and for the same reason: what a *User* pinned should not change because the package was rebuilt. An orchestrator bundles a set of them, and its own package version is packaging only.
