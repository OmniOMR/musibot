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

It receives a representation of the *MusicorpusPage* domain object, which also contains the ID of `42`.

Then it uploads the `image.jpg` file:

```
PUT /musicorpus-pages/42/files/image.jpg
```

Right after that it can start the new *Pipeline Execution*, by sending a JSON payload with the requested *Pipeline* name and version:

```
POST /musicorpus-pages/42/pipeline-executions
```

The response contains a JSON representation of the *PipelineExecution* domain object with the ID equal to `1` (the first execution for this page).

Then it waits for the execution to finish (complete or fail). Later, this will be done consuming an SSE stream, but for now it will do 1s polling at this endpoint:

```
GET /musicorpus-pages/42/pipeline-executions/1
```

It will check the `state` of the execution - whether it's still `running` or is `completed` or `failed`.

We'll assume it completes fine in about 20 seconds.

Now the client downloads the output file by fetching this endpoint:

```
GET /musicorpus-pages/42/files/transcription.musicxml
```

Finally, since it no longer needs the server-side *MusicorpusPage*, it deletes it to free up server resources (if not, the server would evict the page eventually when under disk pressure).

```
DELETE /musicorpus-pages/42
```

Now the python client's `process_page` function returns.


## 3. Web API orders the rest of Musibot to fulfill the request

The `api` service holds the state of the whole Musibot system, therefore it knows about all existing *Musicorpus Pages*. When the `POST /musicorpus-pages` request comes, it simply creates a new in-memory representation of the *MusicorpusPage*, assigns it a new ID and returns it back. No MinIO or RabbitMQ communication is needed.

> **Note:**  Within the `api` service, *Musicorpus Pages* are stored in-memory in a `MusicorpusPageRepository` class instance. This class would abstract away database/redis access, should a database/redis be added later.

> **Note:** To ensure that MinIO does not accidentally hold some old stale data for the just assigned page ID (say from a previous `api` crash); the `api` service performs a complete erasure of the MinIO bucket during `api` service startup.

When input *Files* (say `image.jpg`) are uploaded to the `api` service, it just forwards these writes directly to MinIO, where each *MusicorpusPage* is represented as a bucket top-level folder with the name equal to the page ID.

When a pipeline execution is started, the `api` service creates the *PipelineExecution* domain object and adds it to the proper *MusicorpusPage*, while at the same time dispatching a message to RabbitMQ for Orchestrators, that the given pipeline should be executed and what is the execution ID and page ID.

When the execution ends, the orchestrators notifies the `api` service back thorugh a RabbitMQ message in a different queue. The `api` service updates the state of the domain model.

> **Note:** The execution may also time out, which is also checked by the `api` service and in that case it's the `api` service who declares the *Pipeline Execution* as `failed` and adjusts the domain model. The possibly stray, still running execution is sent a termination message, but it is ok if it remains running somewhere and modifying the *Musicorpus Page* data in MinIO. This data already should not be used, since it has a failed *Pipeline Execution* (which means the data (*Files*) are in an indeterminate state anyways).

After the pipeline execution, the MinIO already holds the modified *Files* (since *Orchestrator* and *Workers* directly modify it).

When the python client asks the `api` service to download *Files* for this *MusicorpusPage*, the `api` service simply fetches that data from MinIO and forwards it to the user, generating a corresponding 404 status code when that *File* is missing.

Finally, the `DELETE` operation remove the page's folder from MinIO and clears the page from the `MusicorpusPageRepository`. It also sends pipeline execution termination messages to orchestrators via RabbitMQ if there is a running pipeline.


## 4. An orchestrator picks up the pipeline execution request

A running *Orchestator* subscribes to RabbitMQ for messages that fit any of its pipeline names and versions. When it receives a message to start a given pipeline, it executes the pipeline's `async` function and waits for it to complete (return or raise). Depending on how the pipeline completed, it sends back to RabbitMQ a pipeline execution completion message.

When a pipeline termintion message is received for a currently running pipeline, the python asyncio task behind that pipeline is cancelled - which raises an exception. Depending on whether this exception is handled, the pipeline will either fail gracefully or just fail with an exception. Either way, no one really expects the results to be read anyways.

All of this logic lives in the *Orchestrator Head*.

Now the pipeline implementation may execute *Models* as it's running. The setup for invoking a *Model* by a *Pipeline* is the same as the invocation of a *Pipeline* by the `api` service. A separate set of queues in RabbitMQ are used for the same kind of communication - start a model execution, wait for model execution completion, possibly send a cancellation message if the pipeline is being cancelled. The only difference is that model executions don't live in the domain model - they are only tracked by the *Orchestrator Head* code and don't care about timeouts. If they start running stray, the pipeline timeout will eventually come from above.


## 5. A worker head picks up a model execution request

A running *Worker Head* subscribes to RabbitMQ for messages that fit its *Model* name and version. When it receives a message to start a model execution it fetches the files listed as the execution's input from the MinIO and mirrors the needed MinIO folder structure locally in the filesystem. Then it puts the invocation request as a JSON object on a new line of the *Model's* standard input and waits for the model to confirm its completion via its standard output.

The *Model* modified the local filesystem mirror of MinIO (of the Musicorpus page we're interested in with this invocation). The *Worker Head* detects which files have been updated and uploads them to MinIO. Then in sends a model execution completion message to RabbitMQ to be picked up by the corresponding *Orchestrator*.


## 6. The model receives the model execution request via stdin

The *Model* process is running and reads instructions from its standard input. These instructions come as sequence of JSON objects, where each is a single command and each occupies one line of the input. So one invocation of the `input()` python function fetches one command.

The model also knows which folder mirrors the MinIO folder structure (which corresponds to the Musicorpus dataset folder structure) so that it know where to operate.

When an execution command arrives, the model reads the corresponding input files from the file system, runs its processing and then writes output files to the file system. Then it sends an "execution completed" message to the *Worker Head* via its standard output - formatted in the same way as the standard input - a JSONL stream.

A *Model* does not multitask, it executes one command at a time.

Logging for the code inside a *Model* (e.g. the `print` function) must be redirected to not interfere with the standard output. It may be redirected to RabbitMQ by being wrapped in specialized messages in the *Model's* standard output, which the *Worker Head* understands as log messages and forwards them to RabbitMQ. They can then be collected up in the *Orchestrator* and become part of the *Pipeline Execution* log and be streamed further through the `api` service via SSE to the web UI where they may be viewed in near real-time by the *User*.
