# deploy

How a running Musibot system is assembled from its components. Full narrative in [../docs/deployment.md](../docs/deployment.md).


## Contents (planned)

- **nginx config** — public entry point; serves the Web UI bundle and reverse-proxies the Web API.
- **docker-compose.yml** — local / dev stack: api + fake orchestrator + RabbitMQ + MinIO + a fake worker. The one-command way to run everything locally.
- **deployment notes** — installing the core services onto Ubuntu VMs, and deploying models (clone + venv + worker head).


## Production

Not Kubernetes. Deployment is manual installation onto plain Ubuntu VMs, matching the university infrastructure. Workers scale per model type by starting more of them during library batch bursts (coordinated with the maintainer, so scaling need not be automatic).
