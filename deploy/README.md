# deploy

How a running Musibot system is assembled from its components. Full narrative in [../docs/deployment.md](../docs/deployment.md).


## Contents

- **[docker-compose.yml](docker-compose.yml)** — the local development stack (see below).
- **[nginx/musibot.conf.template](nginx/musibot.conf.template)** — the public entry point: serves the Web UI bundle and reverse-proxies the Web API, the MinIO S3 endpoint and the MinIO Console. Also where the single-upload size limit lives (see [Public access](../docs/public-access.md)). A template because the deployment addresses differ between a VM and the local stack; everything else is identical, so the local stack exercises this file rather than a copy of it.
- **[nginx/render-config.sh](nginx/render-config.sh)** — renders that template on a VM, which is the job the nginx image's entrypoint does for the compose stack. It substitutes only the `MUSIBOT_*` names the template mentions, because a bare `envsubst` would also eat nginx's own `$host` and `$remote_addr` and produce a configuration that still starts.
- **[nginx/nginx.env.example](nginx/nginx.env.example)** — the addresses that fill that template in.
- **[nginx/university-proxy.conf](nginx/university-proxy.conf)** — local stack only. A stand-in for the university's proxy, which publishes Musibot under a path prefix and strips that prefix before forwarding. It exists to be the thing we do not control.
- **[rabbitmq/20-musibot.conf](rabbitmq/20-musibot.conf)** — publishes the RabbitMQ management UI under the deployment's path prefix. Dropped into RabbitMQ's `conf.d` alongside the image's own defaults.
- **[minio/minio.env.example](minio/minio.env.example)** — VM only. What the .deb's own `minio.service` reads out of `/etc/default/minio`.
- **[systemd/](systemd/)** — the units the VM runs Musibot's own services under: `musibot-api.service`, the templated `musibot-worker@.service` (one unit, any model), and an example environment file for each. Model-specific configuration lives with the model — see [components/models/zeus](../components/models/zeus/README.md).

The runbook that uses all of them is [Deploying onto a VM](../docs/deploying-to-a-vm.md).


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
| RabbitMQ management UI | http://localhost:15672/musibot/rabbitmq/ | `root` / `password` |
| MinIO (S3 API) | `localhost:9000` | `root` / `password` |
| MinIO console | http://localhost:9001 | `root` / `password` |

The management UI sits under a path even on its direct port, because the prefix is RabbitMQ's own setting rather than something nginx applies — it is the path the UI builds its links from, so it has to be the whole public one. `http://localhost:15672` redirects there, so the bare address still works.

The `minio-init` one-shot container creates the buckets that hold *Musicorpus Pages* — a stopped `minio-init` container is the expected steady state. Data lives in named volumes and survives a restart; `docker compose down -v` wipes it. (The `api` service wipes its own keys on startup anyway — see [User request dataflow](../docs/user-request-dataflow.md) — so stale page data is not a concern in practice.)

Credentials are the throwaway `root` / `password` pair used throughout the documentation examples. They are for local development only.


## The published topology

Musibot is not served at the root of a host. It is published at `https://<host>/musibot/` by a proxy that is not ours and that strips the prefix before forwarding, and almost everything about the deployment is shaped by that: nginx's locations, the `api` service's `root_path`, the bucket and key prefix, the Web UI's base path. Browsing a service directly exercises none of it, so the stack can also stand the whole thing up locally.

The `nginx` and `proxy` containers do that. Browse **http://localhost:8000/musibot/**.

| Reached at | Is |
| --- | --- |
| http://localhost:8000/musibot/ | the Web UI |
| http://localhost:8000/musibot/api/ | the Web API (`/musibot/api/docs` for the interactive docs) |
| http://localhost:8000/musibot/s3/ | the MinIO S3 endpoint, where presigned URLs point |
| http://localhost:8000/musibot/minio/ | the MinIO Console |
| http://localhost:8000/musibot/rabbitmq/ | the RabbitMQ management UI |

Two things need doing before this works:

**Build the Web UI.** nginx serves `components/web-ui/dist`, and until `npm run build` has been run there those paths are 404 while everything else still works.

**Start the `api` service and a *Worker* or two.** Neither takes an argument: this topology is what every default is set for.

```bash
components/api/.venv/bin/musibot-api
```

That is the whole of it. The service binds every interface (the nginx container reaches it at `host.docker.internal:8080`), answers under `/musibot/api`, keeps pages in the `musibot` bucket under the `s3/` key prefix, issues presigned URLs against `http://localhost:8000`, and offers the public tier the Web UI needs. Those storage names are what makes a presigned URL survive being served from a path prefix — the bucket is the prefix's first segment and the rest of it is the key prefix — and [Deployment](../docs/deployment.md) explains why there is no other option. Set `MUSIBOT_API_UPSTREAM` if you run the service somewhere other than port 8080.

**To reach MinIO directly instead**, without nginx in front of it, three settings have to be put back:

```bash
components/api/.venv/bin/musibot-api \
    --host 127.0.0.1 \
    --s3-public-url http://localhost:9000 \
    --root-path ""
```

Pages then live in the `musibot` bucket under `s3/` just the same — the rooting costs nothing when nothing is proxied, so it is not worth a fourth flag and a *Worker* that does not know about it. `minio-init` still creates `musibot-pages` for anything configured the old way.


## Production

Not Kubernetes. Deployment is manual installation onto plain Ubuntu VMs, matching the university infrastructure. Workers scale per model type by starting more of them during library batch bursts (coordinated with the maintainer, so scaling need not be automatic).
