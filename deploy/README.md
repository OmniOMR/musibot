# deploy

How a running Musibot system is assembled from its components. Full narrative in [../docs/deployment.md](../docs/deployment.md).


## Contents

- **[docker-compose.yml](docker-compose.yml)** — the local development stack (see below).

Planned:

- **nginx config** — public entry point; serves the Web UI bundle and reverse-proxies the Web API.
- **deployment notes** — installing the core services onto Ubuntu VMs, and deploying models (clone + venv + worker head).


## Local development stack

`docker-compose.yml` brings up the infrastructure that Musibot services connect to — RabbitMQ and MinIO:

```bash
cd deploy
docker compose up -d
```

It deliberately does **not** start Musibot's own services (`api`, *Orchestrators*, *Workers*). Those you start yourself, from your IDE or shell, pointed at this stack — which is what you want while developing them. Plugging a locally-running service into a stack is the same act whether the stack is this one or a production one; see [Writing pipelines](../docs/writing-pipelines.md).

| Service | Address | Credentials |
| --- | --- | --- |
| RabbitMQ (AMQP) | `localhost:5672` | `root` / `password` |
| RabbitMQ management UI | http://localhost:15672 | `root` / `password` |
| MinIO (S3 API) | `localhost:9000` | `root` / `password` |
| MinIO console | http://localhost:9001 | `root` / `password` |

The `minio-init` one-shot container creates the single global bucket, `musibot-pages`, that holds all *Musicorpus Pages* — a stopped `minio-init` container is the expected steady state. Data lives in named volumes and survives a restart; `docker compose down -v` wipes it. (The `api` service wipes the bucket on startup anyway — see [User request dataflow](../docs/user-request-dataflow.md) — so stale page data is not a concern in practice.)

Credentials are the throwaway `root` / `password` pair used throughout the documentation examples. They are for local development only.


## Production

Not Kubernetes. Deployment is manual installation onto plain Ubuntu VMs, matching the university infrastructure. Workers scale per model type by starting more of them during library batch bursts (coordinated with the maintainer, so scaling need not be automatic).
