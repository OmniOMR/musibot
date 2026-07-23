# RabbitMQ exchanges and messages

This page is the index of everything that travels through RabbitMQ — every exchange, who publishes to it, who consumes it, and which messages it carries. It is the counterpart to the [HTTP API](http-api.md) page: that one documents the system's outward contract, this one its internal contract. All internal communication between Musibot services goes through the exchanges listed here.

Each message is a JSON object. Payloads are given in full on the linked pages rather than here; this page is the map.


## Discovery

How the `api` service learns which *Pipelines* and *Models* currently exist. See [Discovery](discovery.md) for the full protocol, the message payloads, and the timing rules. The schemas are implemented in `musibot.core.discovery`, which is also where the exchange names and timings live as constants.

- `musibot.discovery` (fanout) — published to by every *Orchestrator Head* and *Worker Head*, consumed by the `api` service alone.
    - `announcement` — "I exist and here is what I provide": an *Orchestrator Head* announces its set of *Pipelines*, a *Worker Head* the single *Model* it runs. Sent on startup, then every 10 seconds, and in reply to a probe.
    - `goodbye` — sent once on graceful shutdown, so the provider drops out of the listing immediately instead of after its 30-second TTL.
- `musibot.discovery.probe` (fanout) — published to by the `api` service, consumed by every *Orchestrator Head* and *Worker Head*.
    - `probe` — "everyone announce yourselves now", sent on `api` service startup so that a restarted service repopulates its registry within about a second.


## How work is addressed

Both execution protocols below have the same shape, because they are the same problem twice: something asks for a named, versioned thing to be run, without knowing or caring which process will run it.

Work is therefore addressed to a **name and version, never to an instance**. Requests go to a `direct` exchange with the routing key `<name>@<version>`, and the processes that provide that thing bind one shared queue to it. Several instances on that one queue are competing consumers, which is exactly how a *Pipeline* or *Model* scales horizontally: start more of them and the work spreads.

> **Note:** The routing key joins name and version with `@` rather than `.`, and the exchange is `direct` rather than `topic`, because a version like `1.0.0` is full of dots — which a topic exchange would read as segment separators. Musibot never needs wildcard routing, so nothing is lost.

Queues are declared by the consumers, named after what they consume (`musibot.pipeline.hello-world@1.0.0`), and auto-delete when their last consumer disconnects, so a departed *Orchestrator* leaves nothing behind to accumulate messages. Nothing is durable: all of Musibot's state is ephemeral, and a broker restart is a system restart.

If **nobody** provides the requested thing, the exchange has no matching queue and the request is simply dropped. This is not treated as an error at publish time — the `api` service lets the *Pipeline Execution* time out instead, which is the same outcome as an *Orchestrator* that accepted the work and then died, and so needs no separate machinery. Every request also carries a `timeout_seconds`, set as the message's expiration, so a request that reaches a queue nobody is draining expires rather than being run long after anyone cared.


## Pipeline execution

The `api` service asking an *Orchestrator* to run a *Pipeline*, and being told how it went. See [User request dataflow](user-request-dataflow.md) §3 and §4 for the narrative.

A *Pipeline Execution* is identified by the pair `page_id` + `execution_id` — execution IDs are only unique within their page (see the [HTTP API](http-api.md)), so both are always carried together.

- `musibot.pipeline-executions` (direct, key `<name>@<version>`) — published to by the `api` service, consumed by the *Orchestrator Heads* providing that pipeline.
    - `pipeline-execution-start` — run this pipeline against this page.
- `musibot.pipeline-execution-results` (fanout) — published to by *Orchestrator Heads*, consumed by the `api` service.
    - `pipeline-execution-result` — it finished, or it failed.
- `musibot.pipeline-execution-control` (fanout) — published to by the `api` service, consumed by every *Orchestrator Head*.
    - `pipeline-execution-terminate` — stop this execution. Fanned out because the `api` service does not track which *Orchestrator* instance took the work; each one ignores executions it does not have.

```json
{
  "type": "pipeline-execution-start",
  "page_id": "7Kf2mP9xLwQa",
  "execution_id": 1,
  "pipeline": { "name": "hello-world", "version": "1.0.0" },
  "parameters": {},
  "timeout_seconds": 300
}
```

```json
{
  "type": "pipeline-execution-result",
  "page_id": "7Kf2mP9xLwQa",
  "execution_id": 1,
  "state": "completed",
  "error": null,
  "orchestrator": { "name": "reference-orchestrator", "instance_id": "3xQ7nP2vKm9w" }
}
```

A start message is acknowledged the instant execution begins, not when it ends, so a crashed *Orchestrator* never causes the pipeline to be double-started on redelivery — it times out instead. The `api` service is the sole authority on timeouts: if the deadline passes with no result, it declares the execution failed, publishes a terminate, and stops caring about any result that arrives later.


## Model execution

An *Orchestrator* asking a *Worker* to run a *Model*, and being told how it went. See [User request dataflow](user-request-dataflow.md) §4 and §5 for the narrative.

The same shape as above, with two differences. A model execution has an identity of its own, `model_execution_id`, because it does not exist in the domain model and has no page-scoped number to borrow. And its result goes back to *the one requester that asked*, rather than to a single known service: the request carries the AMQP `reply_to` and `correlation_id` properties, and the requester consumes an exclusive queue it declared at startup.

The requester is an *Orchestrator Head* — or the `api` service itself, when it runs an [ImplicitPipeline](domain-model.md). Nothing about these messages distinguishes the two, which is what lets Musibot execute *Models* with no *Orchestrator* deployed at all.

- `musibot.model-executions` (direct, key `<name>@<version>`) — published to by *Orchestrator Heads* and the `api` service, consumed by the *Worker Heads* running that model.
    - `model-execution-start` — run this model against these files.
- *(the requester's own reply queue)* — published to by *Worker Heads*, consumed by the requester.
    - `model-execution-result` — it finished, or it failed.
- `musibot.model-execution-control` (fanout) — published to by requesters, consumed by every *Worker Head*.
    - `model-execution-terminate` — abandon this model execution, if it has not started yet.

```json
{
  "type": "model-execution-start",
  "model_execution_id": "8Lw4tR6yBn1c",
  "model": { "name": "staff-detector", "version": "2026-07-22" },
  "page_id": "7Kf2mP9xLwQa",
  "input": ["image.jpg"],
  "parameters": {},
  "pipeline_execution": { "page_id": "7Kf2mP9xLwQa", "execution_id": 1 },
  "timeout_seconds": 300
}
```

```json
{
  "type": "model-execution-result",
  "model_execution_id": "8Lw4tR6yBn1c",
  "state": "failed",
  "error": "No staves found in the image.",
  "worker": { "name": "staff-detector", "instance_id": "8Lw4tR6yBn1c" }
}
```

`pipeline_execution` travels along so that everything the *Model* logs can be attributed to the *Pipeline Execution* that caused it, without the *Worker Head* having to ask anyone.

> **Note:** Termination is best-effort and only cancels what has not started. A *Model* executes one command at a time and the [worker IPC](worker-ipc.md) has no way to interrupt one, so a *Model* already working runs to completion and its result is discarded. This is deliberate — interrupting a model mid-execution would mean killing the process, and restarting a model that holds gigabytes of weights costs far more than letting one execution finish.


## Logs and progress

Log lines and progress updates streamed from *Models* and *Pipelines* up to the `api` service, which forwards them to the Web UI over SSE. See [User request dataflow](user-request-dataflow.md) §6.

- `musibot.logs` (fanout) — published to by *Worker Heads* and *Orchestrator Heads*, consumed by the `api` service.
    - `log` — one line of output, from a *Model* or a *Pipeline*.
    - `progress` — a fractional progress report.

```json
{
  "type": "log",
  "pipeline_execution": { "page_id": "7Kf2mP9xLwQa", "execution_id": 1 },
  "source": { "kind": "worker", "name": "staff-detector", "instance_id": "8Lw4tR6yBn1c" },
  "level": "info",
  "message": "transcribing staff 3/12",
  "timestamp": "2026-07-23T15:04:05Z"
}
```

Logs travel **straight to the `api` service**, rather than back through the *Orchestrator* that requested the work. A *Model's* output would otherwise have to wait on a *Pipeline* that is busy computing, which is exactly when a *User* most wants to see that something is happening; and it would make every *Orchestrator* a relay for traffic it has no use for. The cost is that each log message must name the *Pipeline Execution* it belongs to — which is why `pipeline_execution` rides along on every model execution.

Log traffic is fire-and-forget. Nothing is acknowledged, retried or ordered across publishers, and a message that arrives after its *Pipeline Execution* has finished is dropped. Logs are for a human watching a page being read, not an audit trail.
