# Architecture

A running Musibot software system has the following components:

**nginx** is the only component exposed to the public internet. It serves the *Web UI* static bundle and reverse-proxies the *Web API* that sits behind it.

**Web UI** is a single-page web application intended for use by the *General public* and by *Model developers*. It provides a UI layer over the *Web API*.

**Python client** is a python package that lets *Libraries* (their developers) and *Model developers* talk to a Musibot server, without needing to use the lower-level HTTP API.

**Web API** is the python process (a service) that serves the public HTTP API; all external components communicate with it. It holds all of the system's state, which is entirely ephemeral — a scan is received, processed within a few minutes, its results are downloaded, and then everything is forgotten. Because it holds this state it is the one service that does *not* horizontally scale, and for that reason it is kept deliberately lightweight and runs no heavy logic. Should it ever need to scale, the ephemeral state (essentially *MusicorpusPage* IDs) would be moved into a Redis store.

**Orchestrators** are services that provide and execute *Pipelines*. This logic is kept out of the *Web API* to provide extensibility (new orchestrators may be plugged-in easily by connecting to the RabbitMQ) and also to provide horizontal scalability (*Pipelines* may run for example OpenCV routines).

**Worker head** is a small process — comparable to the OpenFaaS watchdog — that connects a single *Model* to the rest of the system. It consumes work messages for its one model type from *RabbitMQ*, batches them (to utilize batching in deep-learning models), and runs the *Model* as a child subprocess, feeding it instructions over a dedicated pair of pipes and the filesystem (see [Worker IPC](worker-ipc.md)). This inter-process boundary keeps the *Model* implementation free of any Musibot messaging or storage concerns and lets each model bring its own python version and dependencies.

**Models** perform the actual recognition (usually deep learning models). Each *Model* is run by exactly one *Worker head*. A *Model* only implements the worker-head IPC interface; some models ship inside this repository and others live in their own repositories. Model weights are the responsibility of each model's own repository (GitHub releases, Hugging Face, or baked into the repository — whatever suits that model).

**MinIO** is the object storage service that stores *MusicorpusPages* for *Users*, while they are being processed. It may be accessed by all the internal services.

**RabbitMQ** is the message broker used for communication between all the internal services. It existst to decouple all the plugin-parts of Musibot from the core parts (*Orchestrators* and *Workers*), as well as providing a producer-consumer pattern implementation between *Pipelines* and *Models*. It is also used to stream data and progress updates from *Workers* up to the *Web API*, which streams it further via the SSE protocol to the *Web UI* to make that UI responsive.
