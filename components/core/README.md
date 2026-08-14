# core

Shared Python library depended on by `api`, `orchestrator-head`, `worker-head`, and `python-client`. It is the single source of truth for anything that crosses a process boundary.


## Contains

- **Configuration framework** — `musibot.core.config`, the settings base class and the shared connection blocks every service composes. See [Service configuration](../../docs/service-configuration.md).
- **Logging setup** — `musibot.core.logging`, shared by every service.
- **Musicorpus page model** — `musibot.core.page`: page identity, the file paths a page may contain, and where those map to in storage. A `MusicorpusPage` is a folder of *Files* and a *File* is opaque bytes; what is *inside* a file is governed by the [Musicorpus Specification](https://github.com/OmniOMR/musicorpus/blob/main/docs/musicorpus-specification/musicorpus-specification.md) and is the business of the *Models* and *Pipelines* that read and write them, not of Musibot, which only moves them around.
- **Storage contracts** — also `musibot.core.page`: object keys in MinIO, and the local mirror a *Worker Head* stages for its *Model*.
- **Message / protocol schemas** — the RabbitMQ message shapes, one module per protocol: `musibot.core.discovery`, `musibot.core.execution` (pipeline and model execution) and `musibot.core.logs`. See [RabbitMQ exchanges and messages](../../docs/rabbitmq-exchanges-and-messages.md). These modules also hold the exchange names, routing rules and protocol timings, which are constants rather than settings because every service has to agree on them.

The `musibot.core` package re-exports the general-purpose pieces — settings, logging, page identity — while a protocol module is imported by name, so that `discovery.WorkerAnnouncement` stays readable at the call site.

The `musibot` package is a namespace package shared by every Musibot distribution, so this component provides `musibot.core` and deliberately ships no `musibot/__init__.py`.


## This library performs no I/O

The line worth holding is not "standard library only" — pydantic and pydantic-settings are here. It is that **`core` never opens a socket or a file**: it is types, validation, constants and settings, and nothing in it talks to RabbitMQ or MinIO. Three things depend on that:

- **`python-client` installs on end-user machines.** Its only dependencies are this and `httpx`, and it needs this one for page-path validation and message shapes. Putting aio-pika and boto3 here would hand every external library user an AMQP client and the AWS SDK they will never call.
- **The test suite needs no infrastructure**, which is what makes it the fast one.
- **A wire contract that imports a transport is harder to reimplement**, on the day something that is not python reads these messages.

So `api`, `worker-head` and `orchestrator-head` each own a thin `Broker` over aio-pika and their own storage module over boto3, and the duplication is accepted. It is smaller than it looks: the three storage modules ask genuinely different questions (the `api` service presigns and lists but never touches bytes; the two heads only touch bytes), and of the ~70 shared lines in a `Broker`, none has changed since it was written. What *has* changed — the RabbitMQ 4 durable-queue fix — landed in the role-specific consume method, which a shared class could only have expressed as a flag.

What must not be duplicated is anything two processes could disagree about, and that is why the queue declarations are here rather than in each head. **If a fourth `Broker` appears, or a second cross-cutting broker fix lands, promote the whole thing** into an optional `musibot-core[amqp]` extra rather than copying it again.


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

Semver. This is the wire contract — a breaking change here ripples to the API, orchestrator, worker heads, and client, so bump it deliberately. The version is derived from the `core/v*` git tags rather than written into `pyproject.toml`; see [Versioning and releases](../../docs/versioning-and-releases.md) and [CHANGELOG.md](CHANGELOG.md).
