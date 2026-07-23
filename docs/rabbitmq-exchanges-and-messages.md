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


## Pipeline execution

TODO — the `api` service asking an *Orchestrator* to run a *Pipeline*, and being told how it went. See [User request dataflow](user-request-dataflow.md) §3 and §4 for the narrative.


## Model execution

TODO — an *Orchestrator* asking a *Worker* to run a *Model*, and being told how it went. See [User request dataflow](user-request-dataflow.md) §4 and §5 for the narrative.


## Logs and progress

TODO — log lines and progress updates streamed from *Models* and *Pipelines* up to the `api` service, which forwards them to the Web UI over SSE. See [User request dataflow](user-request-dataflow.md) §6.
