# Repository layout

Musibot is a monorepo. Every deployable piece lives under `components/`, and each is versioned independently rather than in lockstep — `core` and the public HTTP API are the wire contracts to bump most deliberately.


## Components

- `components/core` — shared python library and the single source of truth for anything that crosses a process boundary: the *MusicorpusPage* domain model and the RabbitMQ message protocol. Every other python component depends on it.
- `components/api` — the *Web API* service. Serves the public HTTP API, holds all (ephemeral) state, and is the one service that does not horizontally scale.
- `components/web-ui` — the *Web UI*: a React + TypeScript single-page app (MUI components), served by nginx.
- `components/python-client` — python package wrapping the HTTP API, published to PyPI for external users.
- `components/orchestrator-head` — the Musibot-provided interface layer that an *Orchestrator* runs inside; connects pipeline code to RabbitMQ and MinIO.
- `components/orchestrators` — *Orchestrators* (sets of *Pipelines*) that ship in-repo; others live in their own repositories and depend only on `orchestrator-head`.
- `components/worker-head` — the OpenFaaS-watchdog-like process that runs one *Model* as an isolated subprocess over IPC.
- `components/models` — *Models* that ship in-repo; others live in their own repositories.


## The two head + plugin pairs

Musibot is extensible along two axes that share a shape: a Musibot-owned *head* hosts a pluggable, possibly-external implementation. The two differ in how tightly the plugin is coupled.

| Axis | Head (Musibot-owned) | Plugin (often external) | Coupling |
| --- | --- | --- | --- |
| Pipelines | `orchestrator-head` | `orchestrators` | Tight — runs in the same process and uses domain concepts (reads pages, invokes models). |
| Models | `worker-head` | `models` | Loose — runs the model as an isolated subprocess over stdin / filesystem IPC, so it can bring its own python and dependencies. |


## Other top-level folders

- `docs/` — architecture, domain model, deployment, and this document.
- `deploy/` — nginx config, docker-compose, and deployment notes.
- `.vscode/` and `musibot.code-workspace` — editor setup. Each component has its own virtual environment and its own tool configuration, and VS Code binds an interpreter per workspace *folder*, so opening `musibot.code-workspace` (which makes every component a folder of its own) is what keeps them apart. Opening the repository as a plain folder works too and is wired to `core`.
