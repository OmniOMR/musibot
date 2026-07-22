# orchestrator-head

The Musibot-provided interface layer that a single *Orchestrator* runs inside. It is the counterpart to `worker-head` on the model side, but with the opposite coupling: where a worker head runs its *Model* as an isolated subprocess, an orchestrator head runs its *Orchestrator* **in the same process** — pipeline code is tightly coupled to Musibot's domain (it reads *MusicorpusPage* *Files*, invokes *Models*, and speaks the RabbitMQ / MinIO protocols), so isolating it would only get in the way.


## Responsibilities

- Connect to RabbitMQ and MinIO and expose the pipeline-execution runtime to the hosted *Orchestrator*.
- Receive pipeline-execution requests, run the *Orchestrator*'s *Pipeline* functions, dispatch *Model* work to workers, and stream progress and results back.
- Present the stable Musibot-facing interface so a custom *Orchestrator* only has to implement *Pipelines*.


## Depends on

`core` (the domain model and wire protocol). Unlike the worker head — which is kept deliberately thin — the orchestrator head is meant to be coupled to Musibot's domain.


## Development and testing

Exercised with a trivial reference *Orchestrator* (a pass-through pipeline) — no heavy dependencies needed.


## Deployment

`pip install`ed into an *Orchestrator*'s virtual environment and started with RabbitMQ + MinIO credentials (see `docs/deployment.md`). It is never deployed on its own — it always hosts exactly one *Orchestrator*.


## Versioning

Semver. It is the interface contract that custom orchestrators build against.
