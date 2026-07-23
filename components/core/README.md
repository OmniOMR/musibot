# core

Shared Python library depended on by `api`, `orchestrator-head`, `worker-head`, and `python-client`. It is the single source of truth for anything that crosses a process boundary.


## Contains

- **Configuration framework** — `musibot.core.config`, the settings base class and the shared connection blocks every service composes. See [Service configuration](../../docs/service-configuration.md).
- **Logging setup** — `musibot.core.logging`, shared by every service.
- **Musicorpus page model** — in-code representation of a `MusicorpusPage`, per the [Musicorpus Specification](https://github.com/OmniOMR/musicorpus/blob/main/docs/musicorpus-specification/musicorpus-specification.md). *(not yet implemented)*
- **Message / protocol schemas** — the RabbitMQ work-request, progress, and result message shapes exchanged between the Orchestrator and worker heads. *(not yet implemented)*
- **Storage contracts** — how a page is laid out in MinIO (object keys, blob formats). *(not yet implemented)*

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
