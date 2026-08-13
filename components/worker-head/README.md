# worker-head

A small process — comparable to the [OpenFaaS watchdog](https://docs.openfaas.com/architecture/watchdog/) — that connects one *Model* to Musibot. It is not really a framework: it owns the RabbitMQ consume loop, batching, log forwarding, and MinIO access, and runs the model itself as a child subprocess.


## How it talks to a model

The model runs as a **subprocess**. The worker head feeds it instructions over **a dedicated pair of pipes and the filesystem** (inter-process communication), leaving the model's own stdout and stderr free — they are captured as its log. This boundary is deliberate:

- The model implementation carries no Musibot messaging or storage concerns.
- Each model may use its own python version and its own dependencies — nothing is shared with the worker head's environment except this IPC contract.

The model is started in a session of its own, so a terminal's signals reach this head and not the model: Ctrl+C on a head started from a shell stops the model through the protocol rather than killing it out from under the head. Stopping escalates to the model's *process group*, so workers a model started itself go with it.


## Responsibilities

- Consume work messages for one model type from RabbitMQ and batch them.
- Launch and drive the model subprocess; move page data to and from MinIO.
- Forward whatever the model prints onto `musibot.logs`, announce the *Files* it wrote onto `musibot.file-changes`, and publish results back over RabbitMQ.


## What one execution looks like

1. A `model-execution-start` arrives on the shared queue for this model's name and version. It is acknowledged **immediately** — a *Worker* that dies mid-execution must not have the work redelivered and the model run twice; the execution times out from the `api` service's point of view instead.
2. The *Files* the request declares as input are downloaded from MinIO into a local mirror of the bucket, one folder per *Musicorpus Page*.
3. An `execute` command goes down the command pipe, and the model reports `completed` or `failed` back on the result pipe.
4. Whatever the model created or changed is uploaded, and the page's local mirror is discarded — it is scratch space for one execution, not a cache.
5. The result is published to the queue named by the request's `reply_to`. Who that is — an *Orchestrator Head*, or the `api` service running an *ImplicitPipeline* — is not this head's business.


## What the model prints, and what it wrote

Every line the model writes to stdout or stderr is published on the `musibot.logs` fanout exchange as it is read, and goes **straight to the `api` service** rather than back through whoever asked for the work — see [RabbitMQ exchanges and messages](../../docs/rabbitmq-exchanges-and-messages.md). stdout is forwarded at level `info` and stderr at `warning`. Two lines of this head's own are published alongside them: what the model wrote, and, when an execution fails, why.

Each line is attributed to the *Pipeline Execution* that caused the work, which is why one rides along on every `model-execution-start`. The attribution is whatever the model is currently executing — a model executes one command at a time, so there is never a question of which — and it is *not* cleared when an execution reports. Output and reports arrive on two different pipes, so a model that prints and then immediately reports completion routinely has that last line read afterwards; dropping it would lose exactly the line a *User* was waiting for. Anything printed before the first execution — an import banner, a model announcing its weights — belongs to no execution and stays in this head's own log.

Publishing is fire-and-forget: nothing acknowledges a log line, and a broker that refuses one costs the *User* a line of output rather than the execution.

The same moment produces a second, structured announcement on `musibot.file-changes`: the paths this execution has just uploaded, for a client that wants to *act* on a new *File* rather than read about it. It is published after the upload and never before, since a client told about a *File* that has not reached storage yet would fetch a `404`. It is fire-and-forget for the same reason as the log — object storage is the truth about what a page holds, and a client that misses a notice is a poll away from finding out.


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
