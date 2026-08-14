# Deployment

Musibot is deployed by manual installation onto plain Ubuntu VMs rather than through a container orchestrator such as Kubernetes. This matches the university infrastructure it runs on, where machine provisioning and lifecycle are handled separately, so from Musibot's point of view a deployment is simply an installation onto a blank VM.

This page is the *why*. The step-by-step is [Deploying onto a VM](deploying-to-a-vm.md) — the commands that bring an instance up on a blank machine, and how to update each piece when the source changes.


## Core services

nginx, the *Web API*, *MinIO* and *RabbitMQ* are installed onto the VM(s). nginx is the only public entry point; it serves the *Web UI* bundle, reverse-proxies the *Web API*, and also reverse-proxies the *MinIO* S3 endpoint — clients upload and download *Files* directly to MinIO via presigned URLs, and those URLs must point at a publicly reachable MinIO address. Services find each other through *RabbitMQ* and *MinIO* connection credentials, so the exact per-VM arrangement stays flexible.

The nginx configuration is [`deploy/nginx/musibot.conf.template`](../deploy/nginx/musibot.conf.template), and the local development stack runs that same file behind a stand-in for the university proxy, so the arrangement below can be exercised without deploying it. See [deploy/README.md](../deploy/README.md).


## Published under a path prefix

Musibot is not served at the root of a host. The university proxy publishes it at `https://quest.ms.mff.cuni.cz/musibot/` and forwards to the VM on port 80, **stripping the `/musibot` prefix on the way**. Five things sit under that prefix:

| Public URL | Behind it |
| --- | --- |
| `https://<host>/musibot/` | the *Web UI* |
| `https://<host>/musibot/api/` | the *Web API* |
| `https://<host>/musibot/s3/` | the *MinIO* S3 endpoint |
| `https://<host>/musibot/minio/` | the *MinIO* Console |
| `https://<host>/musibot/rabbitmq/` | the *RabbitMQ* management UI |

The last two are operators' tools rather than public ones. They are published here because the deployment is reached only through this one prefix and there is nowhere else to put them, which is worth remembering: the only thing in front of either is its own login.

Most of what the prefix costs is ordinary. nginx matches unprefixed paths because the prefix is already gone; the *Web UI* is built with a matching `base` so its asset URLs resolve; and the `api` service is given `root_path=/musibot/api` so its interactive docs can build URLs a browser can follow.

The two consoles need more care, and in opposite directions. Both are told the public path they are published at — `MINIO_BROWSER_REDIRECT_URL` and RabbitMQ's `management.path_prefix` — because both build their own links from it. But they then differ on what they expect to be *asked* for:

- **The MinIO Console** serves its assets at its own root and uses a `<base>` tag to point the browser back under the prefix. nginx must therefore **strip** `/minio/`. Forward it and every stylesheet and script comes back as `200 text/html`, because the Console answers unrecognised paths with its SPA fallback instead of a 404, and the page renders unstyled.
- **The RabbitMQ management UI** expects the whole public path, so nginx **puts the prefix back**. Its UI also moves under the prefix on its direct port as a result.

Both are "supports a base path", and they mean different things by it. Worth checking which kind a console is rather than assuming.

The S3 endpoint is the one that is not ordinary, and it constrains how *Files* are stored.


### Why the bucket is named after the URL

Presigned URLs are SigV4, and a SigV4 signature covers the request path and the `Host` header. MinIO recomputes the signature from what it receives, so what it receives has to be, byte for byte, what was signed — and what was signed is the public URL, `https://<host>/musibot/s3/<key>`. Meanwhile MinIO reads the first segment of any path it receives as the bucket name, and its S3 API has no base-path option (only the Console does).

Those two facts leave exactly one arrangement that works. If nginx strips `/musibot/s3/` so the bucket resolves, the path no longer matches what was signed and MinIO answers `SignatureDoesNotMatch`. If it forwards the path whole, MinIO looks for a bucket named `musibot`. So: **name the bucket `musibot` and store every key under `s3/`.** The whole public path then parses correctly as bucket plus key, with nothing rewritten:

```
https://quest.ms.mff.cuni.cz/musibot/s3/aBcD12345678/image.jpg
                             └─────┘ └──────────────────────┘
                             bucket   key
```

nginx puts back the `/musibot` the university proxy took off, and forces the `Host` header to the signed hostname — it is set literally rather than from `$host`, because the signature does not care where a value came from, only what it is, and a literal cannot drift.

In configuration that is `s3_bucket=musibot`, `s3_key_prefix=s3/`, and an `s3_public_url` that is the **origin only** (`https://quest.ms.mff.cuni.cz`) — the prefix is carried by the bucket and key names, not by the URL. `core` routes every key through `ObjectLayout` so that the `api` service and every *Worker Head* cannot disagree about the rooting; two services rooted differently would fail silently, one writing where the other does not look.

This fuses a storage name to a URL, which is not a nice thing to do. The alternatives are worse: switching object stores does not help, because the constraint is SigV4 and path-style addressing rather than MinIO; and putting a signature-validating proxy in front means reimplementing SigV4, where a subtle bug is either a security hole or an intermittent 403.

A deployment served at the root of its own host needs none of this: leave `s3_key_prefix` empty and the bucket is an ordinary bucket again.


## Deploying a model

A key design goal is that deploying a model is cheap and never touches the core Musibot repository. Each model is pip-installable from a GitHub link, and the host machine is expected to already have the required python versions installed (each model may use its own). Deploying a *Model* onto a machine means:

1. Clone the model's repository (or otherwise obtain its pip-installable package).
2. Create a python virtual environment using the python version that model requires, and `pip install` the model into it.
3. Create a virtual environment for the *worker head* on python 3.11 or newer, and `pip install` the worker head into it.
4. Start the *worker head*, pointing it at the *RabbitMQ* and *MinIO* connection credentials and at the command that launches the model.

The *worker head* then registers for that model's work and runs the model as a subprocess. Model weights come from wherever the model's repository keeps them (GitHub releases, Hugging Face, or baked in), which is why weights never live in this repository.


### One venv or two

Steps 2 and 3 describe two separate virtual environments, but they collapse into one whenever the model can live there: if the model runs on python 3.11+ and its dependencies do not conflict with the worker head's, install both into a single venv and point the worker head at the model in that same venv. This is the common case and the simplest one.

The two-venv arrangement is what makes the other cases possible. The worker head depends on `core`, which requires **python 3.11 or newer**, so a model that runs only on python 3.10 — or one whose dependency pins conflict with the worker head's — cannot share an environment with it. Such a model gets its own venv on its own python version, and the worker head launches it by absolute path:

```bash
# the worker head, running from its own python 3.11 venv
/opt/musibot/worker-head/venv/bin/musibot-worker-head \
    --model-command "/opt/musibot/models/staff-detector/venv/bin/python -m staff_detector" \
    --rabbit-host rabbit.internal \
    --s3-endpoint-url http://minio.internal:9000
```

Nothing is shared across that boundary — no python objects, no imported packages, not even a python version. The two processes communicate only over the [worker IPC](worker-ipc.md): JSON lines on a dedicated pair of pipes, plus the filesystem. This is precisely why the worker-head-to-model interface was made an IPC boundary rather than a python API, and a model pinned to an old python is the case that justifies it.


## Deploying an orchestrator

Deploying an *Orchestrator* is similar to deploying a *Model*, except much simpler. The *Orchestrator* may run on the VM where all the core services run (unless scaling becomes an issue) and it is a single process that does not need the complex runtime environment of a *Model*. It just connects to RabbitMQ and MinIO. It runs the same python version as the other core services but should have its own venv due to having custom additional dependencies that may conflict (depends on what its *Pipelines* need).

It needs no state directory either, which is the one way it is simpler than a *Worker*: a *Pipeline* fetches *Files* from object storage as it needs them and writes straight back, rather than working in a local mirror. The step-by-step is [An orchestrator](deploying-to-a-vm.md#8-an-orchestrator), and what a *Pipeline* is written against is [Writing pipelines](writing-pipelines.md).


## API tokens

*Library* users authenticate with API tokens. For now these are kept in a configuration file on the *Web API* host; a database may be introduced later if the config file becomes untenable. Deliberately, no database is introduced just for this one piece of data while everything else is ephemeral.

*General public* users are not identified at all — they mint a throwaway session token that segregates their pages from each other, and the instance is protected by caps on the public tier as a whole (concurrent executions, total storage, session lifetime). This is a deployment-level concern: the caps are `api` service configuration, and the upload size limit is nginx configuration. See [Public access](public-access.md).
