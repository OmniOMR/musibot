# Service configuration

All Musibot services may be configured via command line arguments, environment variables, or a config file. The structure of the config for each may differ, but the configuration framework is the same. This configuration logic and shared configuration blocks are implemented in the `core` component.

Every service here means every Musibot process: the `api` service, every *Orchestrator* (through its *Orchestrator Head*) and every *Worker* (through its *Worker Head*). A *Model* is not configured this way — it is a subprocess and learns everything it needs over [the worker IPC](worker-ipc.md).


## The three sources

A setting may be given in three places. Later ones win:

1. **Defaults** baked into the settings class.
2. **The config file**, a dotenv file — see below.
3. **Environment variables**, prefixed `MUSIBOT_`.
4. **Command line arguments**.

The rule of thumb this ordering encodes: a config file holds the durable configuration of a deployment, environment variables hold what the surrounding system injects (secrets, per-host addresses), and command line arguments are what a human types to override something for one run.

Each field appears in all three sources under the same name, so that knowing one form gives you the others:

| Field | Config file / env var | Command line |
| --- | --- | --- |
| `rabbit_host` | `MUSIBOT_RABBIT_HOST` | `--rabbit-host` |
| `s3_access_key` | `MUSIBOT_S3_ACCESS_KEY` | `--s3-access-key` |

Every service also accepts `--help`, which lists its full set of settings with defaults — that listing, not this page, is the authoritative reference for any one service.


## Config files are dotenv files

The config file is a dotenv file: flat `KEY=value` lines, holding the same keys as the environment variables.

```ini
# /etc/musibot/api.env
MUSIBOT_RABBIT_HOST=rabbit.internal
MUSIBOT_RABBIT_PASSWORD=hunter2
MUSIBOT_S3_ENDPOINT_URL=http://minio.internal:9000
MUSIBOT_S3_PUBLIC_URL=https://musibot.example.org/s3
```

Musibot's configuration is broad but shallow — a handful of connection settings and a few knobs per service — so a flat format costs nothing, and using the same keys for the file and the environment means there is only one name to learn per setting. It also falls out neatly on the deployment side: Musibot is installed onto plain Ubuntu VMs under systemd (see [Deployment](deployment.md)), and a systemd unit can load a dotenv file directly with `EnvironmentFile=`, so the same file works whether it is passed to the process or handed to the service manager.

The file to read is itself a setting, `--config-file` / `MUSIBOT_CONFIG_FILE`. There is no implicit search path — a service with no config file given reads only its environment and command line, which is the normal case in development and in the [docker compose stack](../deploy/README.md).


## Implementation

The framework is [pydantic-settings](https://docs.pydantic.dev/latest/concepts/pydantic_settings/), which covers all three sources, the `--help` output, and validation in one place. `core` provides a `MusibotSettings` base class that wires up the source ordering and the `MUSIBOT_` prefix; each service subclasses it and adds its own fields. Settings are ordinary typed pydantic fields, so a malformed port or a missing required credential fails at startup with a readable error rather than at first use.

Passwords and keys are typed `SecretStr`, so they do not leak into logs or tracebacks. On startup each service logs its effective configuration with those fields masked — the single most useful line in the log when a service is talking to the wrong host.


## Shared blocks

Connection settings are identical across services and live in `core` as mixins, so that a name means the same thing everywhere:

**RabbitMQ** — needed by every service.

| Field | Default | Meaning |
| --- | --- | --- |
| `rabbit_host` | `localhost` | |
| `rabbit_port` | `5672` | |
| `rabbit_user` | `root` | |
| `rabbit_password` | `password` | |
| `rabbit_vhost` | `/` | |

**S3 / MinIO** — needed by every service that touches *Files*.

| Field | Default | Meaning |
| --- | --- | --- |
| `s3_endpoint_url` | `http://localhost:9000` | Where this service reaches MinIO. |
| `s3_access_key` | `root` | |
| `s3_secret_key` | `password` | |
| `s3_bucket` | `musibot-pages` | The single global bucket holding all *Musicorpus Pages*. |
| `s3_public_url` | *(same as `s3_endpoint_url`)* | The address presigned URLs are issued against. |

`s3_public_url` exists because the `api` service issues presigned URLs that a *User* redeems from the public internet, while the service itself reaches MinIO over the internal network — the two addresses differ in production, where MinIO is reverse-proxied by nginx (see [Deployment](deployment.md)). Only the `api` service needs it; it defaults to the internal endpoint, which is correct for development, where they are the same address.

**Logging** — `log_level` and `log_format`, needed by every service.

The defaults throughout are the development defaults: they match the [docker compose stack](../deploy/README.md), so a service started with no configuration at all comes up against a local stack. This is a deliberate trade — it makes getting started frictionless at the cost of default credentials, which is acceptable only because a production deployment must set every one of these anyway, and one of them is `s3_public_url`, without which nothing works.


## What is not configuration

Some values that look configurable are deliberately constants in `core` instead:

- **The [discovery](discovery.md) heartbeat interval and entry TTL** — every service must agree on them, and nothing good comes of one *Worker* announcing on a different schedule from the rest.
- **Exchange and queue names** — part of the wire protocol (see [RabbitMQ exchanges and messages](rabbitmq-exchanges-and-messages.md)), not of a deployment.

The test is whether two Musibot processes could hold different values and still work together. If not, it belongs in `core` as a constant.
