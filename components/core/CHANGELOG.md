# Changelog for `core`

Released as `core/vX.Y.Z` git tags — see [Versioning and releases](../../docs/versioning-and-releases.md).

This component is the wire contract, so a breaking change here ripples to the `api` service, worker heads, orchestrator heads and the client. Entries are written from the point of view of a component that depends on it.


## Unreleased

Nothing yet.


## 0.1.0 — 2026-07-27

First prototype release. Everything below is new.


### Added

- **Configuration framework** (`musibot.core.config`) — a `MusibotSettings` base class over [pydantic-settings](https://docs.pydantic.dev/latest/concepts/pydantic_settings/) that every service subclasses. Settings resolve from defaults, then a dotenv config file, then `MUSIBOT_`-prefixed environment variables, then command line arguments, and each field appears in all three forms under the same name. Credentials are typed `SecretStr` so they do not leak into logs or tracebacks. See [Service configuration](../../docs/service-configuration.md).
- **Shared connection blocks** — RabbitMQ, S3 / MinIO and logging settings as mixins, so that a setting name means the same thing in every service. Defaults point at the [local development stack](../../deploy/README.md).
- **Logging setup** (`musibot.core.logging`) — shared by every service, with the effective configuration logged at startup and secrets masked.
- **Musicorpus page model** (`musibot.core.page`) — page identity, the *Files* a *MusicorpusPage* may contain, the object keys those map to in storage, and the local mirror a *Worker Head* stages for its *Model*. Page IDs and file paths are validated and anything that could escape a page's folder is refused, symbolic links included.
- **Message schemas**, one module per protocol — `musibot.core.discovery`, `musibot.core.execution` (pipeline and model execution) and `musibot.core.logs`. These modules also hold the exchange names, routing rules and protocol timings, which are constants rather than settings because every service has to agree on them. See [RabbitMQ exchanges and messages](../../docs/rabbitmq-exchanges-and-messages.md).


### Notes

- Requires **python 3.11+**. Through `worker-head` this becomes the floor for any environment a worker head runs in, so it is a constraint on *Models* too.
- Dependencies are deliberately minimal (`pydantic`, `pydantic-settings`) so that every consumer can depend on this without conflicts.
- Ships `musibot.core` as part of the `musibot` namespace package and carries `py.typed`; it deliberately has no `musibot/__init__.py`.
