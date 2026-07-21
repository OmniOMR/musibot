# Architecture

A running Musibot software system has the following components:

**Web UI** is a single-page web application intended for use by the *General public* and by *Model developers*. It provides a UI layer over the *Web API*.

**Python client** is a python package that lets *Libraries* (their developers) and *Model developers* talk to a Musibot server, without needing to use the lower-level HTTP API.

**Web API** is the python process (a service) that serves the public HTTP API and all external components communicate with it. The process may or may not house the **Orchestrator**, which is the service that executes *Pipelines*. *Orchestrator* may also be running as a standalone process (or multiple) to make pipeline execution horizontally scalable.

**Workers** are separate processes that house *Models*. Each *Worker* has one *Model* loaded and waits for requests to process some data by that *Model*.

**MinIO** is the object storage service that stores *MusicorpusPages* for *Users*, while they are being processed. It may be accessed by all the internal services.

**RabbitMQ** is the message broker used for communication between all the internal services. It mainly exists to decouple *Workers* from the *Orchestrator*. *Orchestrator* posts work messages into the broker and each *Worker* consumes work messages for its *Model* type. It also consumes many messages at once to utilize batching (for deep learning models). It is also used to stream data and progress updates from *Workers* up to the *Web API*, which streams it further via SSE protocol to the *Web UI* to make that UI responsive. The broker is also used for communication between the *Web API* and all *Orchestrator* instances, in case the *Orchestrator* is a separate process.
