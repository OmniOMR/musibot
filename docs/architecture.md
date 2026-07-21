# Architecture

A running Musibot software system has the following components:

**nginx** is the only component exposed to the public internet. It serves the *Web UI* static bundle and reverse-proxies the *Web API* that sits behind it.

**Web UI** is a single-page web application intended for use by the *General public* and by *Model developers*. It provides a UI layer over the *Web API*.

**Python client** is a python package that lets *Libraries* (their developers) and *Model developers* talk to a Musibot server, without needing to use the lower-level HTTP API.

**Web API** is the python process (a service) that serves the public HTTP API; all external components communicate with it. It holds all of the system's state, which is entirely ephemeral — a scan is received, processed within a few minutes, its results are downloaded, and then everything is forgotten. Because it holds this state it is the one service that does *not* horizontally scale, and for that reason it is kept deliberately lightweight and runs no heavy logic. Should it ever need to scale, the ephemeral state (essentially *MusicorpusPage* IDs) would be moved into a Redis store.

**Orchestrator** is the service that executes *Pipelines*. It is kept out of the *Web API* because pipeline execution can be heavy (for example running OpenCV routines) and must be able to scale horizontally, which the *Web API* cannot. It runs as one or more standalone processes.

**Worker head** is a small process — comparable to the OpenFaaS watchdog — that connects a single *Model* to the rest of the system. It consumes work messages for its one model type from *RabbitMQ*, batches them (to utilize batching in deep-learning models), and runs the *Model* as a child subprocess, feeding it instructions over standard input and the filesystem. This inter-process boundary keeps the *Model* implementation free of any Musibot messaging or storage concerns and lets each model bring its own python version and dependencies.

**Models** perform the actual recognition (usually deep learning models). Each *Model* is run by exactly one *Worker head*. Most models live in their own repositories and only implement the worker-head IPC interface; a few reference models may ship inside this repository. Model weights are the responsibility of each model's own repository (GitHub releases, Hugging Face, or baked into the repository — whatever suits that model).

**MinIO** is the object storage service that stores *MusicorpusPages* for *Users*, while they are being processed. It may be accessed by all the internal services.

**RabbitMQ** is the message broker used for communication between all the internal services. It mainly exists to decouple *Worker heads* from the *Orchestrator*. The *Orchestrator* posts work messages into the broker and each *Worker head* consumes work messages for its *Model* type. It also consumes many messages at once to utilize batching (for deep learning models). It is also used to stream data and progress updates from *Worker heads* up to the *Web API*, which streams it further via the SSE protocol to the *Web UI* to make that UI responsive. The broker is also used for communication between the *Web API* and all *Orchestrator* instances.
