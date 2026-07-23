# core

Shared Python library depended on by `api`, `orchestrator-head`, `worker-head`, and `python-client`. It is the single source of truth for anything that crosses a process boundary.


## Contains

- **Configuration framework** — `musibot.core.config`, the settings base class and the shared connection blocks every service composes. See [Service configuration](../../docs/service-configuration.md).
- **Logging setup** — `musibot.core.logging`, shared by every service.
- **Musicorpus page model** — `musibot.core.page`: page identity, the file paths a page may contain, and where those map to in storage. A `MusicorpusPage` is a folder of *Files* and a *File* is opaque bytes; what is *inside* a file is governed by the [Musicorpus Specification](https://github.com/OmniOMR/musicorpus/blob/main/docs/musicorpus-specification/musicorpus-specification.md) and is the business of the *Models* and *Pipelines* that read and write them, not of Musibot, which only moves them around.
- **Storage contracts** — also `musibot.core.page`: object keys in MinIO, and the local mirror a *Worker Head* stages for its *Model*.
- **Message / protocol schemas** — the RabbitMQ message shapes, one module per protocol: `musibot.core.discovery` today (see [Discovery](../../docs/discovery.md)); the pipeline-execution, model-execution and log messages are still to come. These modules also hold the exchange names and the protocol timings, which are constants rather than settings because every service has to agree on them.

The `musibot.core` package re-exports the general-purpose pieces — settings, logging, page identity — while a protocol module is imported by name, so that `discovery.WorkerAnnouncement` stays readable at the call site.

The `musibot` package is a namespace package shared by every Musibot distribution, so this component provides `musibot.core` and deliberately ships no `musibot/__init__.py`.


## Development

Pure library, no runtime process. Requires **python 3.11+**, which through `worker-head` becomes the floor for any environment a worker head runs in. Keep dependencies minimal so every consumer can depend on it without conflicts — a *Model* that can meet both constraints shares the worker head's venv, and one that cannot falls back to its own venv across the IPC boundary (see `docs/deployment.md`).

```bash
cd components/core
python3 -m venv .venv
.venv/bin/pip install -e '.[dev]'
```

Other components depend on this one by relative path, so an editable install here is picked up by all of them.


## Testing

Unit tests only; fast, no external services. Schema round-trip and serialization tests.

```bash
.venv/bin/python -m pytest
.venv/bin/python -m ruff check .
.venv/bin/python -m ruff format --check .
.venv/bin/python -m mypy
```

Type checking is `mypy --strict` (configured in `pyproject.toml`, so plain `mypy` suffices), including the tests. The `pydantic.mypy` plugin is required: without it, mypy synthesizes `__init__` from the model's fields and rejects the settings machinery's own keyword arguments.


## Versioning

Semver. This is the wire contract — a breaking change here ripples to the API, orchestrator, worker heads, and client, so bump it deliberately.
