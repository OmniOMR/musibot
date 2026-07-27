# worker-head

A small process — comparable to the [OpenFaaS watchdog](https://docs.openfaas.com/architecture/watchdog/) — that connects one *Model* to Musibot. It is not really a framework: it owns the RabbitMQ consume loop, batching, progress reporting, and MinIO access, and runs the model itself as a child subprocess.


## How it talks to a model

The model runs as a **subprocess**. The worker head feeds it instructions over **a dedicated pair of pipes and the filesystem** (inter-process communication), leaving the model's own stdout and stderr free — they are captured as its log. This boundary is deliberate:

- The model implementation carries no Musibot messaging or storage concerns.
- Each model may use its own python version and its own dependencies — nothing is shared with the worker head's environment except this IPC contract.


## Responsibilities

- Consume work messages for one model type from RabbitMQ and batch them.
- Launch and drive the model subprocess; move page data to and from MinIO.
- Stream progress and results back over RabbitMQ.


## What one execution looks like

1. A `model-execution-start` arrives on the shared queue for this model's name and version. It is acknowledged **immediately** — a *Worker* that dies mid-execution must not have the work redelivered and the model run twice; the execution times out from the `api` service's point of view instead.
2. The *Files* the request declares as input are downloaded from MinIO into a local mirror of the bucket, one folder per *Musicorpus Page*.
3. An `execute` command goes down the command pipe, and the model reports `completed` or `failed` back on the result pipe.
4. Whatever the model created or changed is uploaded, and the page's local mirror is discarded — it is scratch space for one execution, not a cache.
5. The result is published to the queue named by the request's `reply_to`. Who that is — an *Orchestrator Head*, or the `api` service running an *ImplicitPipeline* — is not this head's business.


## Depends on

`core` only. Kept thin so it adds almost nothing to a model's environment when installed alongside it.


## Development

```bash
cd components/worker-head
python3 -m venv .venv
.venv/bin/pip install -e ../core -e '.[dev]'
```

Run it against the [local development stack](../../deploy/README.md) and the [hello-model](../models/hello-model/README.md), which needs no arguments beyond the command that launches the model, since every other default already points at that stack:

```bash
.venv/bin/musibot-worker-head \
    --model-command "../models/hello-model/.venv/bin/python -m hello_model"
```


## Configuration

Beyond the shared RabbitMQ, MinIO and logging blocks (see [service configuration](../../docs/service-configuration.md)):

| Setting | Meaning |
| --- | --- |
| `model_command` | **Required.** The command that launches the *Model*, split as a shell would split it. Usually an absolute path into the model's own virtual environment. |
| `pages_dir` | Where the local mirror lives. A temporary directory is used when unset, which is the normal case. |
| `model_ready_timeout_seconds` | How long to wait for the model to say `ready`. Generous by default — this is where a model loads its weights. |


## Testing

The model side is a real subprocess over real pipes, driven by a scriptable fake model, because descriptor passing, flushing, EOF and a process that dies are exactly what in-memory streams would not exercise. Only RabbitMQ and MinIO are faked.

```bash
.venv/bin/python -m pytest
.venv/bin/python -m ruff check .
.venv/bin/python -m ruff format --check .
.venv/bin/python -m mypy
```


## Not yet implemented

- **Batching.** A model's `supports_batching` is read and announced, but every execution is currently sent as its own `execute` command and no `execute-batch` is ever issued. A batching model therefore works correctly, just without the throughput it could have.
- **Log forwarding.** A model's stdout and stderr are captured and drained — which they must be, or a model blocks on its next `print` — but they go to this head's own log rather than onto `musibot.logs` for the `api` service to stream to the Web UI. Same for `progress` messages.


## Deployment

`pip install`ed into a virtual environment on python 3.11+ (the floor `core` sets) and started with RabbitMQ + MinIO credentials plus the command that launches its model (see `docs/deployment.md`). It is never deployed on its own — always together with exactly one model.

That environment may be the model's own venv, and usually is. It has to be a separate one when the model cannot live there — a model pinned to python 3.10, or with conflicting dependency pins — in which case the worker head launches it by absolute path from its own venv. Nothing crosses that boundary but the IPC contract, which is the point of making it IPC.


## Versioning

Two numbers live here, and they are not the same one:

- **This component's version** — semver, derived from the `worker-head/v*` git tags rather than written into `pyproject.toml`. It versions the implementation: this process, its RabbitMQ and MinIO behaviour, its configuration and its CLI. See [Versioning and releases](../../docs/versioning-and-releases.md) and [CHANGELOG.md](CHANGELOG.md).
- **The IPC protocol version** — a single integer, `1` today, which a *Model* declares in its `ready` message and this head checks for exact equality. It versions the [worker IPC contract](../../docs/worker-ipc.md) and moves far more rarely.

Keeping the IPC contract stable is the obligation that matters to *Models*, and it is what "do not break this casually" refers to — but the mechanical compatibility check is the integer, not this component's semver, which a *Model* never sees. See [the protocol version](../../docs/worker-ipc.md#the-protocol-version) for when each one moves.


## Naming

"Worker head" is a working name (it is the OpenFaaS-watchdog-like piece). Rename the folder and references if a better name emerges.
