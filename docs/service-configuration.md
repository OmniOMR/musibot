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
MUSIBOT_S3_PUBLIC_URL=https://musibot.example.org
MUSIBOT_S3_BUCKET=musibot
MUSIBOT_S3_KEY_PREFIX=s3/
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
| `s3_bucket` | `musibot` | The single global bucket holding all *Musicorpus Pages*. |
| `s3_public_url` | *(same as `s3_endpoint_url`; the `api` service defaults it to `http://localhost:8000`)* | The address presigned URLs are issued against. |
| `s3_key_prefix` | `s3/` | A prefix every object key is stored under. |

`s3_public_url` exists because the `api` service issues presigned URLs that a *User* redeems from the public internet, while the service itself reaches MinIO over the internal network — the two addresses differ in production, where MinIO is reverse-proxied by nginx (see [Deployment](deployment.md)). Only the `api` service needs it, and only it overrides the default: the local stack's public origin, so that a browser redeems a URL through nginx exactly as it will in a deployment. A service run against MinIO directly sets it to the endpoint.

`s3_bucket` and `s3_key_prefix` are ordinary-looking settings that are anything but, once a deployment is published under a path prefix rather than at the root of a host. A SigV4 signature covers the request path, and MinIO reads the first segment of the path it receives as the bucket, so an instance served at `https://host/musibot/s3/` has to be configured with `s3_bucket=musibot` and `s3_key_prefix=s3/` — the storage names absorb the URL, because nothing is allowed to rewrite the path. [Deployment](deployment.md) sets out why there is no alternative. Unlike `s3_public_url`, these are needed by **every** service that touches *Files*: two services rooted differently do not fail, they simply stop seeing each other's objects.

**Logging** — `log_level` and `log_format`, needed by every service.

The defaults throughout are the development defaults: they match the [docker compose stack](../deploy/README.md) **as it is published** — through nginx, under `/musibot/`, which is the topology a deployment runs. So `docker compose up` and then a service with no arguments at all is the whole of starting Musibot locally, and what you are then running is shaped the way production is: the same `root_path`, the same bucket and key prefix, the same public origin. Reaching MinIO directly instead is the arrangement that now needs flags, and [deploy/README.md](../deploy/README.md) says which.

This is a deliberate trade — it makes getting started frictionless at the cost of default credentials and a service that listens on every interface — and it is acceptable only because a deployment sets every one of these explicitly. [`deploy/systemd/api.env.example`](../deploy/systemd/api.env.example) does, `host` included; a VM that copied it is not running on any of these defaults.


## What is not configuration

Some values that look configurable are deliberately constants in `core` instead:

- **The [discovery](discovery.md) heartbeat interval and entry TTL** — every service must agree on them, and nothing good comes of one *Worker* announcing on a different schedule from the rest.
- **Exchange and queue names** — part of the wire protocol (see [RabbitMQ exchanges and messages](rabbitmq-exchanges-and-messages.md)), not of a deployment.

The test is whether two Musibot processes could hold different values and still work together. If not, it belongs in `core` as a constant.
