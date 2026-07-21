# Deployment

Musibot is deployed by manual installation onto plain Ubuntu VMs rather than through a container orchestrator such as Kubernetes. This matches the university infrastructure it runs on, where machine provisioning and lifecycle are handled separately, so from Musibot's point of view a deployment is simply an installation onto a blank VM.


## Core services

nginx, the *Web API*, the *Orchestrator*, *MinIO* and *RabbitMQ* are installed onto the VM(s). nginx is the only one exposed publicly; it serves the *Web UI* bundle and reverse-proxies the *Web API*. Services find each other through *RabbitMQ* and *MinIO* connection credentials, so the exact per-VM arrangement stays flexible.


## Deploying a model

A key design goal is that deploying a model is cheap and never touches the core Musibot repository. Each model is pip-installable from a GitHub link, and the host machine is expected to already have the required python versions installed (each model may use its own). Deploying a *Model* onto a machine means:

1. Clone the model's repository (or otherwise obtain its pip-installable package).
2. Create a python virtual environment using the python version that model requires.
3. `pip install` the model and the *worker head* into that environment.
4. Start the *worker head*, pointing it at the *RabbitMQ* and *MinIO* connection credentials.

The *worker head* then registers for that model's work and runs the model as a subprocess. Model weights come from wherever the model's repository keeps them (GitHub releases, Hugging Face, or baked in), which is why weights never live in this repository.


## API tokens

*Library* users authenticate with API tokens. For now these are kept in a configuration file on the *Web API* host; a database may be introduced later if the config file becomes untenable. Deliberately, no database is introduced just for this one piece of data while everything else is ephemeral. Authentication for *General public* users is still an open question — one candidate is issuing a token per client IP address and rate-limiting on it.
