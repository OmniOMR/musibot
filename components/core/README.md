# core

Shared Python library depended on by `api`, `orchestrator-head`, `worker-head`, and `python-client`. It is the single source of truth for anything that crosses a process boundary.


## Contains

- **Musicorpus page model** — in-code representation of a `MusicorpusPage`, per the [Musicorpus Specification](https://github.com/OmniOMR/musicorpus/blob/main/docs/musicorpus-specification/musicorpus-specification.md).
- **Message / protocol schemas** — the RabbitMQ work-request, progress, and result message shapes exchanged between the Orchestrator and worker heads.
- **Storage contracts** — how a page is laid out in MinIO (object keys, blob formats).


## Development

Pure library, no runtime process. Requires **python 3.11+**, which through `worker-head` becomes the floor for any environment a worker head runs in. Keep dependencies minimal so every consumer can depend on it without conflicts — a *Model* that can meet both constraints shares the worker head's venv, and one that cannot falls back to its own venv across the IPC boundary (see `docs/deployment.md`).


## Testing

Unit tests only; fast, no external services. Schema round-trip and serialization tests.


## Versioning

Semver. This is the wire contract — a breaking change here ripples to the API, orchestrator, worker heads, and client, so bump it deliberately.
