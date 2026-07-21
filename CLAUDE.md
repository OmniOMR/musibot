# Musibot

Musibot is a web service for Optical Music Recognition (OMR): it reads scans and photos of sheet music and produces machine-readable output such as MusicXML. See [README.md](README.md) and the [docs/](docs/) folder for the full architecture.


## Repository layout

This is a monorepo. Each deployable piece lives under `components/` and is versioned independently (not in lockstep). `core` and the HTTP API are the wire contracts to bump deliberately.

- `components/core` — shared python library: musicorpus page model and RabbitMQ message protocol.
- `components/api` — Web API; holds all (ephemeral) state and is the one service that does not horizontally scale.
- `components/orchestrator` — executes pipelines; kept separate from the Web API so it can scale.
- `components/worker-head` — OpenFaaS-watchdog-like process that runs one model as a subprocess over IPC.
- `components/models` — reference models shipped in-repo; most models live in their own repositories.
- `components/python-client` — PyPI package wrapping the HTTP API.
- `components/web-ui` — TypeScript single-page app, served by nginx.
- `deploy/` — nginx config, docker-compose, and deployment notes.


## Markdown conventions

Match the repository's existing markdown style when creating or editing `.md` files:

- Leave exactly one blank line after a heading.
- Leave exactly two blank lines before a heading (unless the heading is the first line of the file).
- Do not hard-wrap paragraphs — write each paragraph as a single line and let the editor soft-wrap it. Explicit wrapping leaves stray single words on their own lines in the author's editor.
