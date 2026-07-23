# Deployment

Musibot is deployed by manual installation onto plain Ubuntu VMs rather than through a container orchestrator such as Kubernetes. This matches the university infrastructure it runs on, where machine provisioning and lifecycle are handled separately, so from Musibot's point of view a deployment is simply an installation onto a blank VM.


## Core services

nginx, the *Web API*, *MinIO* and *RabbitMQ* are installed onto the VM(s). nginx is the only public entry point; it serves the *Web UI* bundle, reverse-proxies the *Web API*, and also reverse-proxies the *MinIO* S3 endpoint — clients upload and download *Files* directly to MinIO via presigned URLs, and those URLs must point at a publicly reachable MinIO address. Services find each other through *RabbitMQ* and *MinIO* connection credentials, so the exact per-VM arrangement stays flexible.


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
/opt/musibot/worker-head/.venv/bin/musibot-worker-head \
    --model-command "/opt/musibot/models/staff-detector/.venv/bin/python -m staff_detector" \
    --rabbit-host rabbit.internal \
    --s3-endpoint-url http://minio.internal:9000
```

Nothing is shared across that boundary — no python objects, no imported packages, not even a python version. The two processes communicate only over the [worker IPC](worker-ipc.md): JSON lines on the model's standard input and output, plus the filesystem. This is precisely why the worker-head-to-model interface was made an IPC boundary rather than a python API, and a model pinned to an old python is the case that justifies it.


## Deploying an orchestrator

Deploying an *Orchestrator* is similar to deploying a *Model*, except much simpler. The *Orchestrator* may run on the VM where all the core services run (unless scaling becomes an issue) and it is a single process that does not need the complex runtime environment of a *Model*. It just connects to RabbitMQ and MinIO. It runs the same python version as the other core services but should have its own venv due to having custom additional dependencies that may conflict (depends on what its *Pipelines* need).


## API tokens

*Library* users authenticate with API tokens. For now these are kept in a configuration file on the *Web API* host; a database may be introduced later if the config file becomes untenable. Deliberately, no database is introduced just for this one piece of data while everything else is ephemeral. Authentication for *General public* users is still an open question — one candidate is issuing a token per client IP address and rate-limiting on it.
