# User request dataflow

This documentation section walks through one music page being uploaded to Musibot and recognized by a pipeline with two models. It describes all the communication that happens between all the services in order to fulfill the task. The pipeline used is the one described in the [Writing pipelines](writing-pipelines.md) guide. 


## 1. User invokes the python client

The *User* sends a page for execution with a pipeline, as described by the [Using python client](using-python-client.md) guide:

```py
output_files = client.process_page(
    input={
        "image.jpg": Path("my-page-scan.jpg").read_bytes()
    },
    pipeline=("hello-world", "1.0.0"),
    output={"transcription.musicxml"}
)
```


## 2. Python client talks to the web API

The python client first creates an empty *MusicorpusPage*:

```
POST /musicorpus-pages
```

It receives a representation of the *MusicorpusPage* domain object, which also contains the ID of `7Kf2mP9xLwQ`.

Then it obtains a presigned MinIO URL for uploading the `image.jpg` file:

```
POST /musicorpus-pages/7Kf2mP9xLwQ/file-urls
{ "put": ["image.jpg"] }
```

The response maps `image.jpg` to a short-lived presigned URL, and the client `PUT`s the file bytes straight to that URL — directly to MinIO, not through the `api` service (which does not horizontally scale and is kept out of the file byte-path).

Right after that it can start the new *Pipeline Execution*, by sending a JSON payload with the requested *Pipeline* name and version:

```
POST /musicorpus-pages/7Kf2mP9xLwQ/pipeline-executions
```

The response contains a JSON representation of the *PipelineExecution* domain object with the ID equal to `1` (the first execution for this page).

Then it waits for the execution to finish (complete or fail). Later, this will be done consuming an SSE stream, but for now it will do 1s polling at this endpoint:

```
GET /musicorpus-pages/7Kf2mP9xLwQ/pipeline-executions/1
```

It will check the `state` of the execution - whether it's still `running` or is `completed` or `failed`.

We'll assume it completes fine in about 20 seconds.

Now the client obtains a presigned download URL and fetches the output file directly from MinIO:

```
POST /musicorpus-pages/7Kf2mP9xLwQ/file-urls
{ "get": ["transcription.musicxml"] }
```

It then `GET`s the file bytes straight from the returned MinIO URL.

Finally, since it no longer needs the server-side *MusicorpusPage*, it deletes it to free up server resources (if not, the server would evict the page eventually when under disk pressure).

```
DELETE /musicorpus-pages/7Kf2mP9xLwQ
```

Now the python client's `process_page` function returns.


## 3. Web API orders the rest of Musibot to fulfill the request

The `api` service holds the state of the whole Musibot system, therefore it knows about all existing *Musicorpus Pages*. When the `POST /musicorpus-pages` request comes, it simply creates a new in-memory representation of the *MusicorpusPage*, assigns it a new ID and returns it back. No MinIO or RabbitMQ communication is needed.

> **Note:** Each *MusicorpusPage* is owned by the *User* whose API token created it, and every later operation on it (upload, execute, download, delete) is authorized against that ownership — a *User* can only touch their own pages. Page IDs are 12-character NanoIDs (random and URL-safe, such as `7Kf2mP9xLwQ`) rather than sequential integers, so they cannot be guessed or enumerated across users; this is defense-in-depth on top of the ownership check. *Pipeline Execution* IDs stay small per-page integers, since reaching one already requires access to its page.

> **Note:**  Within the `api` service, *Musicorpus Pages* are stored in-memory in a `MusicorpusPageRepository` class instance. This class would abstract away database/redis access, should a database/redis be added later.

> **Note:** To ensure that MinIO does not accidentally hold some old stale data for the just assigned page ID (say from a previous `api` crash); the `api` service performs a complete erasure of the MinIO bucket during `api` service startup.

To upload or download *Files*, the client first calls `POST /musicorpus-pages/{id}/file-urls`. The `api` service authorizes the request against page ownership, sanitizes the requested paths, and returns short-lived presigned MinIO URLs. The client then transfers the file bytes directly to and from MinIO, so the `api` service is never in the file byte-path. Each *MusicorpusPage* is represented in MinIO as a top-level folder (inside one global bucket) with the name equal to the page ID.

When a pipeline execution is started, the `api` service creates the *PipelineExecution* domain object and adds it to the proper *MusicorpusPage*, while at the same time dispatching a message to RabbitMQ for Orchestrators, that the given pipeline should be executed and what is the execution ID and page ID.

When the execution ends, the orchestrators notifies the `api` service back through a RabbitMQ message in a different queue. The `api` service updates the state of the domain model.

> **Note:** The execution may also time out, which is also checked by the `api` service and in that case it's the `api` service who declares the *Pipeline Execution* as `failed` and adjusts the domain model. The possibly stray, still running execution is sent a termination message, but it is ok if it remains running somewhere and modifying the *Musicorpus Page* data in MinIO. This data already should not be used, since it has a failed *Pipeline Execution* (which means the data (*Files*) are in an indeterminate state anyways).

After the pipeline execution, the MinIO already holds the modified *Files* (since *Orchestrator* and *Workers* directly modify it).

When the client asks for a presigned download URL, the `api` service returns one pointing at the *File* in MinIO; the client fetches it straight from MinIO. A request for a missing *File* yields a 404 directly from MinIO.

Finally, the `DELETE` operation remove the page's folder from MinIO and clears the page from the `MusicorpusPageRepository`. It also sends pipeline execution termination messages to orchestrators via RabbitMQ if there is a running pipeline.


## 4. An orchestrator picks up the pipeline execution request

A running *Orchestrator* subscribes to RabbitMQ for messages that fit any of its pipeline names and versions. When it receives a message to start a given pipeline, it executes the pipeline's `async` function and waits for it to complete (return or raise). Depending on how the pipeline completed, it sends back to RabbitMQ a pipeline execution completion message.

> **Note:** An *Orchestrator* acknowledges the RabbitMQ start message the instant it begins the execution (just before invoking the `async` function), not after it finishes. A crashed *Orchestrator* therefore never causes the message to be redelivered and the pipeline double-started; the *Pipeline Execution* simply times out from the `api` service's point of view. The same applies to *Model* executions. From the `api` service's perspective a *Pipeline Execution* is `running` the moment its start message is posted to RabbitMQ — so if no *Orchestrator* ever consumes it, the message times out inside RabbitMQ and the execution is declared timed-out just the same.

When a pipeline termination message is received for a currently running pipeline, the python asyncio task behind that pipeline is cancelled - which raises an exception. Depending on whether this exception is handled, the pipeline will either fail gracefully or just fail with an exception. Either way, no one really expects the results to be read anyways.

All of this logic lives in the *Orchestrator Head*.

Now the pipeline implementation may execute *Models* as it's running. The setup for invoking a *Model* by a *Pipeline* is the same as the invocation of a *Pipeline* by the `api` service. A separate set of queues in RabbitMQ are used for the same kind of communication - start a model execution, wait for model execution completion, possibly send a cancellation message if the pipeline is being cancelled. The only difference is that model executions don't live in the domain model - they are only tracked by the *Orchestrator Head* code and don't care about timeouts. If they start running stray, the pipeline timeout will eventually come from above.


## 5. A worker head picks up a model execution request

A running *Worker Head* subscribes to RabbitMQ for messages that fit its *Model* name and version. When it receives a message to start a model execution it fetches the files listed as the execution's input from the MinIO and mirrors the needed MinIO folder structure locally in the filesystem. Then it puts the invocation request as a JSON object on a new line of the *Model's* standard input and waits for the model to confirm its completion via its standard output.

The *Model* modifies the local filesystem mirror of MinIO (of the Musicorpus page we're interested in with this invocation). The *Worker Head* detects which files have been updated and uploads them to MinIO. Then it sends a model execution completion message to RabbitMQ to be picked up by the corresponding *Orchestrator*.

> **Note:** If the *Model* subprocess exits without confirming completion (for example, it crashes), the *Worker Head* notices the process exit and reports the model execution as failed, which propagates up and fails the *Pipeline Execution*. The precise handshake will be specified later in the Worker IPC interface document.

Some *Models* support **batching** to better utilize deep-learning hardware. Because not every model can batch, batching is opt-in and exposed as a *separate IPC command*: a model that does not implement it advertises so and only ever receives single-execution commands. For a batchable *Model*, the *Worker Head* accumulates several pending model-execution requests from RabbitMQ (possibly originating from different *Pipeline Executions*) and dispatches them to the model as one batch command. The model processes all samples together (e.g. in a single forward pass) and reports a completion for each. The local MinIO filesystem mirror is unaffected — it is simply shared by all samples in the batch, each operating within its own *Musicorpus Page* folder in the mirror.


## 6. The model receives the model execution request via stdin

The *Model* process is running and reads instructions from its standard input. These instructions come as sequence of JSON objects, where each is a single command and each occupies one line of the input. So one invocation of the `input()` python function fetches one command.

The model also knows which folder mirrors the MinIO folder structure (which corresponds to the Musicorpus dataset folder structure) so that it knows where to operate.

When an execution command arrives, the model reads the corresponding input files from the file system, runs its processing and then writes output files to the file system. Then it sends an "execution completed" message to the *Worker Head* via its standard output - formatted in the same way as the standard input - a JSONL stream.

A *Model* does not multitask, it executes one command at a time.

Logging for the code inside a *Model* (e.g. the `print` function) must be redirected to not interfere with the standard output. It may be redirected to RabbitMQ by being wrapped in specialized messages in the *Model's* standard output, which the *Worker Head* understands as log messages and forwards them to RabbitMQ. They can then be collected up in the *Orchestrator* and become part of the *Pipeline Execution* log and be streamed further through the `api` service via SSE to the web UI where they may be viewed in near real-time by the *User*.
