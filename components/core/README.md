# core

Shared Python library depended on by `api`, `orchestrator`, `worker-head`, and `python-client`. It is the single source of truth for anything that crosses a process boundary.


## Contains

- **Musicorpus page model** — in-code representation of a `MusicorpusPage`, per the [Musicorpus Specification](https://github.com/OmniOMR/musicorpus/blob/main/docs/musicorpus-specification/musicorpus-specification.md).
- **Message / protocol schemas** — the RabbitMQ work-request, progress, and result message shapes exchanged between the Orchestrator and worker heads.
- **Storage contracts** — how a page is laid out in MinIO (object keys, blob formats).


## Development

Pure library, no runtime process. Keep dependencies minimal so every consumer can depend on it without conflicts — this is the one package that every isolated model environment must also be able to install.


## Testing

Unit tests only; fast, no external services. Schema round-trip and serialization tests.


## Versioning

Semver. This is the wire contract — a breaking change here ripples to the API, orchestrator, worker heads, and client, so bump it deliberately.
