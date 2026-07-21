# web-ui

Single-page web application for the *General public* and *Model developers*. A UI layer over the Web API.


## Responsibilities

- Upload page scans (JPEG), pick a pipeline, watch live progress via the API's SSE stream.
- View and download recognition results.


## Stack

React single-page app, written in TypeScript, using MUI (Material UI) components.


## Development

Dev server proxying to a local `api` (compose). Node toolchain, separate from the python side.


## Testing

Component / unit tests; optionally end-to-end (Playwright) against a compose server.


## Deployment

Built to a static bundle and served by nginx, which also reverse-proxies the Web API behind the same origin (see `docs/deployment.md`).


## Versioning

Own version, decoupled from the API version it targets (negotiated over HTTP).
