# orchestrator

Executes *Pipelines*: it orchestrates individual *Model* invocations to turn an input `MusicorpusPage` (e.g. a JPEG scan) into new data (e.g. MusicXML). It is a separate, horizontally-scalable service — kept out of the Web API because a pipeline can run heavy logic (such as OpenCV routines).


## Responsibilities

- Consume pipeline-execution requests from the Web API (via RabbitMQ).
- Run the pipeline (an `async` python function held in memory for the few minutes it executes).
- Dispatch model work to worker heads over RabbitMQ and collect their results.
- Stream progress back up to the Web API.


## Depends on

`core`. At runtime: RabbitMQ and MinIO.


## Development

Run against a local compose stack (RabbitMQ + MinIO + a fake worker head).


## Testing

- Unit tests for pipeline logic.
- Integration tests exercising a full pipeline against fake models.


## Deployment

Installed onto VM(s); scale by running more instances during library batch bursts (see `docs/deployment.md`).


## Versioning

Semver.
