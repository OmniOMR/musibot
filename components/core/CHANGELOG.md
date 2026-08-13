# Changelog for `core`

Released as `core/vX.Y.Z` git tags — see [Versioning and releases](../../docs/versioning-and-releases.md).

This component is the wire contract, so a breaking change here ripples to the `api` service, worker heads, orchestrator heads and the client. Entries are written from the point of view of a component that depends on it.


## Unreleased


### Removed

- **`ProgressMessage` and everything that reported a fraction.** The `musibot.logs` exchange now carries `log` messages and nothing else, and `parse_log_message` returns a `LogMessage` rather than a union — a publisher still sending `progress` is refused by the parser instead of being taken for a log. Progress reporting was never implemented and is not going to be: an execution takes a second or two, and the models Musibot runs cannot honestly say how far along they are — a detector produces every box at the end of one forward pass, and an autoregressive model does not know how many tokens it is about to emit. A log line is the whole of what a *User* is told while they wait.


## 0.2.0 — 2026-08-07

*Signatures* become patterns rather than fixed *File* paths, and a deployment can be rooted under a key prefix inside its bucket. Both are changes to the wire contract, so every component that depends on `core` moves with it.


### Added

- **`s3_key_prefix` and `ObjectLayout`** — where in a bucket a deployment keeps its pages. A new `S3Settings` field, empty by default, and a layout object reached through `S3Settings.object_layout` that builds every key from it. **Every service that touches *Files* must build keys through the layout rather than calling `object_key` directly**, and every service in one deployment must be configured with the same prefix: two rooted differently do not fail, they simply stop seeing each other's objects.

  It exists because of how a deployment is published. Presigned URLs are SigV4 and the signature covers the request path, while MinIO reads the first path segment of what it receives as the bucket — so an instance served under a URL prefix has to spend that prefix's first segment on the bucket name and carry the rest as a key prefix, because nothing is permitted to rewrite the path. See [Deployment](../../docs/deployment.md).


### Changed

- **`Signature` entries are patterns, not *File* paths** (`musibot.core.patterns`). A whole path segment may now be a slot — `{}` and `{name}` for one subdivision instance, `{*}` and `{*name}` for all of them, with a repeated name binding two slots to the same instance or the same set — so that a *Model* can declare `Staves/{s}/image.jpg` and mean it of any page. The wire shape is unchanged, still two arrays of strings, and every *Signature* written before this is still valid. `Signature.check_input` decides whether an input list fits, and `Signature.promised_output_files` names the outputs it guarantees outright. See [Signatures](../../docs/signatures.md).
- **`PipelineExecutionStart` carries `input`** — the *Files* the execution is about. It never had one: an explicit *Pipeline* was dispatched with a page ID and nothing saying what to operate on. Unlike `ModelExecutionStart.input` it does not bound what may be read.
- **`{` and `}` are refused in a *File* path** (`validate_file_path`), so a pattern never needs an escape and a page can never hold a file whose name looks like a slot. Nothing in the Musicorpus Specification names a file this way.


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
