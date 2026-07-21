# worker-head

A small process — comparable to the [OpenFaaS watchdog](https://docs.openfaas.com/architecture/watchdog/) — that connects one *Model* to Musibot. It is not really a framework: it owns the RabbitMQ consume loop, batching, progress reporting, and MinIO access, and runs the model itself as a child subprocess.


## How it talks to a model

The model runs as a **subprocess**. The worker head feeds it instructions over **standard input and the filesystem** (inter-process communication). This boundary is deliberate:

- The model implementation carries no Musibot messaging or storage concerns.
- Each model may use its own python version and its own dependencies — nothing is shared with the worker head's environment except this IPC contract.


## Responsibilities

- Consume work messages for one model type from RabbitMQ and batch them.
- Launch and drive the model subprocess; move page data to and from MinIO.
- Stream progress and results back over RabbitMQ.


## Depends on

`core` only. Kept thin so it adds almost nothing to a model's environment when installed alongside it.


## Development and testing

Exercised with a trivial fake model (identity / echo) that speaks the IPC contract — no ML dependencies needed.


## Deployment

`pip install`ed into a model's virtual environment and started with RabbitMQ + MinIO credentials (see `docs/deployment.md`). It is never deployed on its own — always together with exactly one model.


## Versioning

Semver. The IPC contract between the worker head and models is the interface to keep stable; a model records the worker-head version it targets.


## Naming

"Worker head" is a working name (it is the OpenFaaS-watchdog-like piece). Rename the folder and references if a better name emerges.
