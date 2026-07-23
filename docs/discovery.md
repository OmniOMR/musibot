# Discovery

Musibot has no registry of what exists. *Orchestrators* and *Workers* are plugged into a running system just by connecting to RabbitMQ (see the [Domain model](domain-model.md) FAQ), which means nothing can be listed in a configuration file — a developer may attach an in-development *Orchestrator* running on their laptop at any moment, and detach it just as abruptly. Yet the `api` service must answer `GET /pipelines`, and it must know which *Models* exist in order to offer an *ImplicitPipeline* for each of them.

Discovery is how the `api` service learns this. Every *Orchestrator Head* and every *Worker Head* periodically announces what it provides; the `api` service listens and keeps an in-memory registry of what it has heard about recently.


## Discovery never routes work

The registry the `api` service builds is used for **listing and validation only**. It is never used to route work — routing is RabbitMQ's job, and the `api` service addresses a *Pipeline Execution* to a pipeline name and version, not to a particular *Orchestrator* instance.

This is what keeps discovery cheap: it is allowed to be wrong. It is a cache of announcements with a timeout, so it lags reality by seconds in both directions:

- A *Pipeline* may be listed just after its last *Orchestrator* died. Executing it dispatches a message that no one consumes, and the *Pipeline Execution* times out — exactly as it would if the *Orchestrator* had died one moment later, mid-execution. This failure mode already exists and is already handled (see [User request dataflow](user-request-dataflow.md) §4).
- A *Pipeline* may be missing from the listing for a few seconds after its *Orchestrator* started. Executing it would work, but the `api` service rejects it with a `404` — because a typo in a pipeline name is far more common than a request racing a fresh deployment, and failing immediately beats timing out a minute later.

Because of this, discovery deliberately has no consistency guarantees, no persistence, and no coordination between announcers. It is not a service registry; it is a directory that expires.


## The announcement protocol

Announcements travel over a fanout exchange, `musibot.discovery`. Every head publishes to it and the `api` service binds one exclusive, auto-delete queue to it. Nothing else consumes it.

A head announces:

- **on startup**, immediately;
- **every 10 seconds** thereafter (the *heartbeat interval*);
- **on demand**, when the `api` service probes (see below);
- **once with a goodbye**, on graceful shutdown.

The `api` service drops a provider from its registry when it has heard nothing from it for **30 seconds** (the *entry TTL*, three missed heartbeats), or immediately upon a goodbye. A provider killed with `SIGKILL` therefore lingers for up to 30 seconds; a provider stopped gracefully disappears at once.


### Orchestrator announcement

An *Orchestrator Head* announces the whole set of *Pipelines* its *Orchestrator* provides:

```json
{
  "type": "announcement",
  "provider": {
    "kind": "orchestrator",
    "name": "reference-orchestrator",
    "instance_id": "3xQ7nP2vKm9w",
    "head_version": "0.1.0"
  },
  "pipelines": [
    {
      "name": "hello-world",
      "version": "1.0.0",
      "signature": {
        "input": ["image.jpg"],
        "output": ["transcription.musicxml"]
      }
    }
  ]
}
```


### Worker announcement

A *Worker Head* announces the single *Model* it runs:

```json
{
  "type": "announcement",
  "provider": {
    "kind": "worker",
    "name": "staff-detector",
    "instance_id": "8Lw4tR6yBn1c",
    "head_version": "0.1.0"
  },
  "model": {
    "name": "staff-detector",
    "version": "2026-07-22",
    "signature": {
      "input": ["image.jpg"],
      "output": ["layout.json"]
    },
    "supports_batching": true
  }
}
```

A *Worker* provides exactly one *Model*, so `provider.name` is that *Model's* name and the payload is a single `model` object rather than a list.


### Goodbye

```json
{
  "type": "goodbye",
  "provider": { "kind": "worker", "name": "staff-detector", "instance_id": "8Lw4tR6yBn1c" }
}
```


### Probe

A restarted `api` service starts with an empty registry, and waiting up to a full heartbeat interval to become useful is a poor first impression — especially in development, where the `api` service is restarted constantly. So on startup the `api` service publishes a probe to a second fanout exchange, `musibot.discovery.probe`:

```json
{ "type": "probe" }
```

Every head binds an exclusive, auto-delete queue to that exchange and answers with its ordinary announcement, delayed by a random 0–1 second so that a hundred *Workers* do not reply in the same instant. The registry is therefore populated within about a second of the `api` service starting.

The probe is an optimization, not a mechanism of its own — a head that ignored probes entirely would still be discovered by its next heartbeat.


## The registry

Within the `api` service, announcements are folded into a `ProviderRegistry` — the discovery counterpart to the `MusicorpusPageRepository`, and equally in-memory and equally ephemeral. Entries are keyed by `instance_id`, so multiple instances of the same *Orchestrator* or *Model* are tracked separately.

From those entries the service derives the *Pipeline* listing:

- Each announced *Pipeline* becomes a listing entry keyed by name and version. Several *Orchestrator* instances announcing the same name and version are the horizontal-scaling case and collapse into one entry.
- Each announced *Model* additionally yields an **[ImplicitPipeline](domain-model.md)** with the same name and version as the *Model*, marked as such in the listing.

```
GET /pipelines

200 OK
{
  "pipelines": [
    {
      "name": "hello-world",
      "version": "1.0.0",
      "signature": { "input": ["image.jpg"], "output": ["transcription.musicxml"] },
      "implicit": false,
      "orchestrators": ["reference-orchestrator"],
      "instances": 2
    },
    {
      "name": "staff-detector",
      "version": "2026-07-22",
      "signature": { "input": ["image.jpg"], "output": ["layout.json"] },
      "implicit": true,
      "orchestrators": [],
      "instances": 5
    }
  ],
  "warnings": []
}
```

`instances` is the number of live announcers behind the entry. It is exposed because it is the one number that explains an otherwise baffling situation to a *Model developer*: a *Pipeline* that is listed but whose executions all time out has zero instances of some *Model* it depends on. It is a diagnostic, not a capacity figure — a *Worker* announces that it exists, not how busy it is.


## Conflicts

Two providers may announce the same name and version while being genuinely different things. Musibot cannot detect this and does not try; announcements are trusted. What it can detect, it reports:

- **Same pipeline name and version from two *Orchestrators* with differing signatures** (`conflicting-signatures`) — identical signatures are assumed to be the horizontal-scaling case; differing ones cannot be.
- **A *Pipeline* name colliding with a *Model* name** (`name-collision`) — the [Domain model](domain-model.md) requires these namespaces not to overlap, since an *ImplicitPipeline* takes its *Model's* name. The explicit *Pipeline* wins the listing entry and the *ImplicitPipeline* is suppressed.

Neither is resolved automatically — they are operator errors, and the fix is to stop announcing the conflicting thing.

Both are written to the `api` service's log **and** returned in the `warnings` array of the `GET /pipelines` response, alongside the `pipelines` array:

```json
{
  "pipelines": [ "..." ],
  "warnings": [
    {
      "type": "conflicting-signatures",
      "message": "Pipeline 'hello-world' version '1.0.0' is announced with differing signatures by orchestrators 'reference-orchestrator' and 'my-laptop-orchestrator'.",
      "pipeline": { "name": "hello-world", "version": "1.0.0" }
    },
    {
      "type": "name-collision",
      "message": "Pipeline 'staff-detector' version '2026-07-22' from orchestrator 'reference-orchestrator' collides with a model of the same name and version; the implicit pipeline for that model is suppressed.",
      "pipeline": { "name": "staff-detector", "version": "2026-07-22" }
    }
  ]
}
```

Surfacing them over HTTP and not only in the log is deliberate. The person who causes a conflict is typically a *Model developer* who has just plugged an in-development *Orchestrator* into a shared system from their laptop — precisely the person with no access to the `api` service's log. They see the effect (their pipeline is listed but behaves as someone else's) with no way to reach the explanation. Putting it in the listing response means the Web UI can show it, and it costs nothing while there are no conflicts: `warnings` is then an empty array.

A warning is a property of the system as a whole, not of any single *Pipeline*, so warnings sit at the top level rather than being attached to entries. `message` is human-readable and its wording is not a contract; `type` is.


## Open questions

- **Signature representation** — the examples above spell a *Signature* as flat lists of *File* paths, which cannot express "one `transcription.musicxml` per staff, however many staves there are". The [Musicorpus Specification](https://github.com/OmniOMR/musicorpus/blob/main/docs/musicorpus-specification/musicorpus-specification.md) has the vocabulary for this; the wire shape needs to be settled when *Signature* is implemented in `core`.
- **Loose version selection** — the listing is exact name-plus-version. Whether a *User* may ask for "the newest `1.x` of `hello-world`" is an open question shared with [Writing pipelines](writing-pipelines.md), and would be resolved against this listing.
- **Announcement authenticity** — anything able to reach RabbitMQ can announce anything, including a *Pipeline* name that shadows a real one. Musibot's internal network is trusted today; if that changes, this exchange is one of the places it shows.
