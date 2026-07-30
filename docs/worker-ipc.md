# Worker IPC

This page specifies the interface between a *Worker Head* and the *Model* it runs. It is the contract a *Model* implements — the only thing Musibot asks of it — and it is deliberately small: a *Model* knows nothing of RabbitMQ, MinIO, *Pipelines* or *Users*.

The *Worker Head* starts the *Model* once, as a child process, and keeps it running. Commands and results travel over two pipes as JSON lines; the data itself travels through the filesystem.


## Why a process boundary at all

A *Model* is not imported as a python library but launched as a separate process, because that is what lets it bring its own python version and its own dependencies. `core` requires python 3.11+, so a model that runs only on python 3.10 could not share an environment with the *Worker Head* even in principle (see [Deployment](deployment.md)); and deep-learning models pin conflicting versions of the same handful of libraries as a matter of routine. Across a process boundary none of that has to be reconciled.

What crosses the boundary is therefore only bytes: JSON lines on two dedicated pipes, and files in a directory.


## The channels

Four channels connect the two processes, and it matters which is which:

| Channel | Direction | Carries |
| --- | --- | --- |
| The **command pipe** | head → model | Commands, as JSON lines. |
| The **result pipe** | model → head | Results and progress, as JSON lines. |
| **stdout and stderr** | model → head | Whatever the model prints. Captured as its log. |
| The **page directory** | both | The files a command reads and writes. |

The protocol runs on two dedicated file descriptors — **not** on stdin and stdout. The *Worker Head* creates a pipe pair, passes it to the child (`subprocess.Popen(..., pass_fds=...)`), and tells the model which descriptor numbers to use through the environment:

| Environment variable | Meaning |
| --- | --- |
| `MUSIBOT_IPC_COMMAND_FD` | The descriptor the model **reads** commands from. |
| `MUSIBOT_IPC_RESULT_FD` | The descriptor the model **writes** results to. |
| `MUSIBOT_PAGES_DIR` | The directory holding the *Musicorpus Page* folders. |
| `PYTHONUNBUFFERED` | Set to `1`, so that the model's log output is not held in a buffer (see below). |

On the model side, opening them is the whole of the setup:

```py
import os

commands = os.fdopen(int(os.environ["MUSIBOT_IPC_COMMAND_FD"]), "r")
results = os.fdopen(int(os.environ["MUSIBOT_IPC_RESULT_FD"]), "w")
```

The descriptor numbers are given in the environment rather than fixed at 3 and 4 so that nothing on either side hardcodes them.

> **Note:** Passing file descriptors to a child this way is POSIX-only — it does not work on Windows. Musibot is deployed on Ubuntu, and a *Model* must therefore be tested against a *Worker Head* on Linux, whatever platform it was developed on. A model developer working on Windows can write the model anywhere, but has to reach a Linux machine (or WSL) before it can be run under a *Worker Head*.


### Why not stdin and stdout

Because a *Model* would then have to never print anything, and that is not a promise an ML codebase can keep. TensorFlow and friends write banners and warnings to stdout and stderr at import time, and a `print()` left in during debugging would corrupt the protocol rather than merely being untidy. Running the protocol on stdin and stdout — as the Language Server Protocol, MCP and the OpenFaaS classic watchdog all do — makes "never write to stdout" a rule the model author must remember, and the failure when they forget is a baffling one.

Two dedicated descriptors cost about five lines in the model and remove the whole class of problem. They also turn the model's stdout and stderr from a hazard into a feature: both are captured by the *Worker Head* and forwarded as that model's log, so `print("staff 3/12")` reaches the *Pipeline Execution* log and, through the `api` service's SSE stream, the Web UI. A *Model* needs no logging setup at all.

> **Note:** Because that stdout is a pipe rather than a terminal, it is block-buffered by default, and log lines would reach the *User* in delayed clumps — which defeats the point of streaming them. The *Worker Head* therefore starts the *Model* with `PYTHONUNBUFFERED=1` in its environment. A *Model* not written in python has to arrange the equivalent itself, or its logs will lag.


### Writing a message

Every message is one JSON object on one line, UTF-8, terminated by `\n`, and **flushed immediately**:

```py
results.write(json.dumps(message) + "\n")
results.flush()   # without this the message sits in a buffer and the head waits forever
```

A pipe is block-buffered, so an unflushed message is not merely late — it is invisible until enough output accumulates, which for a model reporting one completion at a time is never. This is the single easiest way to get a *Model* wrong.


## The page directory

`MUSIBOT_PAGES_DIR` points at a directory in which each *Musicorpus Page* is a folder named by its page ID, mirroring the layout in MinIO:

```
<MUSIBOT_PAGES_DIR>/
  7Kf2mP9xLwQ/
    image.jpg
    Staves/
      1/
        image.jpg
```

Before sending a command, the *Worker Head* downloads that command's declared input *Files* from MinIO into this mirror. After the command completes, it uploads the files the *Model* created or changed. A *Model* therefore reads and writes ordinary local files and never speaks to object storage.

A *Model* must confine itself to the page folders named in the command it is currently executing. Nothing else in the directory is its business, and paths that escape a page folder are rejected by the *Worker Head*.


## The protocol version

The protocol has a version of its own: an integer, `1` today, which a *Model* declares in its `ready` message and a *Worker Head* checks for exact equality. A model announcing anything else is refused rather than driven on a guess.

It is deliberately an integer and not a semver string. The thing that has to compare it is a *Model* — possibly not written in python, and whose whole obligation here is meant to fit in the thirty lines at the end of this page. `if version != 1: fail` is a comparison anyone can write correctly in any language; parsing and ordering `1.2.0` against `1.10.0` is not. Semver would also imply a negotiation — does a head speaking `1.2` accept a model speaking `1.3`? — that nothing here wants. There is one authority defining these versions and no independent implementations to reconcile, so a single equality check is the whole compatibility story.

The constant lives in `worker-head` (`musibot.worker_head.model_process.IPC_VERSION`) rather than in `core`, which holds the RabbitMQ protocol constants. Unlike those, this contract has only one Musibot-side speaker: a *Model* is not a Musibot process and imports nothing from us.


### It is not the `worker-head` version

These are two different numbers and conflating them will mislead you. `worker-head` is a python distribution versioned with semver from git tags (see [Versioning and releases](versioning-and-releases.md)); `ipc_version` versions the wire contract specified on this page — much as OpenSSH 9.6 speaks SSH protocol 2.

| | `worker-head` version | `ipc_version` |
| --- | --- | --- |
| Versions | The implementation: the process, its RabbitMQ and MinIO behaviour, its configuration and its CLI. | The contract on this page: which messages exist, what fields they carry, and the rules of the exchange. |
| Form | Semver — `0.1.0` | One integer — `1` |
| Travels | Outward over RabbitMQ, to the `api` service. | Inward over the result pipe, from the *Model*. |
| Who reads it | The `api` service, as reported detail about a running *Worker*. | The *Worker Head*, deciding whether it can drive this *Model* at all. |
| How often it moves | Every release. | Rarely; most protocol growth does not need it. |

They do not even travel on the same channel. A *Worker Head* looks its own version up at runtime with `importlib.metadata.version("musibot-worker-head")` — so it is whatever was installed, which is now whatever the git tags said — and publishes it as `head_version` in its [discovery](discovery.md) announcements. `ipc_version` never leaves the pipes.

The relationship between them runs one way: a change to `ipc_version` is necessarily a change to `worker-head` and forces a version bump there, while `worker-head` bumps repeatedly without the protocol moving at all. The knowledge is one-directional too — a *Model* never learns the head's version, while the head checks the model's integer before it will run it.

So when the [worker-head README](../components/worker-head/README.md) describes its semver as covering "the IPC contract", it means the practical obligation: do not break models casually. The mechanical compatibility check is `ipc_version`, and nothing else.


### When to bump it

Most growth does not need a bump, because [unknown message types are ignored in both directions](#rules-of-the-exchange), and a new head → model message can be gated behind a capability the *Model* advertises — the way `execute-batch` is gated behind `supports_batching`. Bump `ipc_version` only when a change would make an existing, correct *Model* behave incorrectly:

- a field or message is removed or renamed, or changes its meaning or type
- the head begins to require behaviour a model could not have known to implement — a new message it expects a reply to, unconditionally, with no capability flag guarding it
- a rule of the exchange changes, such as one command at a time

Adding an optional model → head message, adding a capability-gated command, or changing anything purely on the head's side of the pipe — batching internals, log forwarding, configuration — does not qualify.

If a bump ever happens, a *Worker Head* may come to accept a set of versions rather than a single one, but only for versions it can genuinely drive. The check exists to refuse guesses, not to paper over them.


## The messages

Every message is a JSON object carrying a `type`, written on one line and flushed. What follows is every type the protocol defines; anything else is ignored by both sides.


### `ready` — model → head

Sent once, at startup, before anything else. It tells the *Worker Head* what it is hosting:

```json
{
  "type": "ready",
  "ipc_version": 1,
  "model": {
    "name": "staff-detector",
    "version": "2026-07-22",
    "signature": {
      "input": ["image.jpg"],
      "output": ["layout.json"]
    },
    "supports_batching": true
  }
}
```

The *Model* is the source of truth for its own name, version and signature — it is the thing that knows them — and the *Worker Head* republishes them when it announces itself (see [Discovery](discovery.md)). This also gates readiness usefully: the *Worker Head* consumes no work from RabbitMQ and announces nothing until its model has said `ready`, so a model that spends a minute loading its weights is simply not offered work during that minute.

The `signature` says which sets of *Files* the *Model* admits, not which *Files* any one execution will bring: a staff-level model announces `"input": ["Staves/{s}/image.jpg"]` and is handed one staff at a time. [Signatures](signatures.md) defines the notation, and is worth reading before writing one — in particular, a *Model* that treats instances independently should declare one at a time and set `supports_batching`, rather than asking for all of them with `{*}`, because only the former can report a single bad staff as a single failure.

The *Worker Head* fails an execution whose *Model* reported success without writing an output the `signature` promises outright — that is, a slot-free, non-optional entry. Files the *Model* writes that the `signature` does not describe are still sent back, and logged.


### `execute` — head → model

One model execution. The *Model* reads the input files, does its work, writes its output files, and reports.

```json
{
  "type": "execute",
  "execution_id": "e7c1",
  "page": "7Kf2mP9xLwQ",
  "input": ["image.jpg"],
  "parameters": {}
}
```

`execution_id` is opaque to the *Model* and is echoed back in its report. `input` is the *Files* the *Worker Head* has staged, and the only ones it has: they are concrete paths, chosen by whoever requested the execution, never the patterns of the `signature`. A *Model* whose signature is `Staves/{s}/image.jpg` therefore reads `Staves/7/image.jpg` here and writes its output beside it. `parameters` is a free-form JSON object, model-specific, passed through from the *Pipeline* that requested the execution — this is where a pipeline hands a model its knobs.


### `execute-batch` — head → model

Sent only to a *Model* that advertised `supports_batching`. It carries several executions to be processed together, which is what lets a deep-learning model fill a single forward pass:

```json
{
  "type": "execute-batch",
  "executions": [
    { "execution_id": "e7c1", "page": "7Kf2mP9xLwQ", "input": ["Staves/1/image.jpg"], "parameters": {} },
    { "execution_id": "e7c2", "page": "7Kf2mP9xLwQ", "input": ["Staves/2/image.jpg"], "parameters": {} },
    { "execution_id": "9a04", "page": "Qm3vN8xTrb2", "input": ["Staves/1/image.jpg"], "parameters": {} }
  ]
}
```

The executions in a batch may come from different *Pipeline Executions* and different *Musicorpus Pages*, as the last one above does. The *Model* reports each execution separately, with one `completed` or `failed` per `execution_id`, in any order; the batch is finished when all of them have been reported. One failing sample therefore does not fail the others.


### `completed` and `failed` — model → head

```json
{ "type": "completed", "execution_id": "e7c1" }
```

```json
{ "type": "failed", "execution_id": "e7c1", "error": "No staves found in the image." }
```

The `error` string is propagated up into the *Pipeline Execution* log, so it is worth writing for a human.


### `progress` — model → head

Optional, sent any number of times while an execution is running:

```json
{ "type": "progress", "execution_id": "e7c1", "message": "staff 3/12", "fraction": 0.25 }
```

Anything the *Model* prints is already captured as a log line, so `progress` is only needed when progress must be attributed to a *specific* execution — which in practice means during a batch, where the *Worker Head* cannot tell which sample a printed line belongs to and attributes it to all of them.


### `shutdown` — head → model

```json
{ "type": "shutdown" }
```

Sent when the *Worker Head* is stopping. The *Model* should finish what it is doing, exit, and stop reading commands. The *Worker Head* then closes the command pipe, waits briefly, and escalates to `SIGTERM` and `SIGKILL` if the process is still alive.


## Rules of the exchange

- **One command at a time.** A *Model* does not multitask. The *Worker Head* sends no further command until every execution in the current one has been reported. A *Model* may therefore be written as a plain loop, with no concurrency of any kind.
- **A closed command pipe means stop.** Reading EOF on the command pipe is equivalent to `shutdown` — it is what the *Model* sees if the *Worker Head* dies.
- **A dead model fails its work.** If the *Model* process exits, or its result pipe reaches EOF, every execution in flight is reported as failed up the chain, which fails the *Pipeline Execution*. The *Worker Head* then restarts the model and, once it says `ready` again, resumes taking work.
- **Unknown message types are ignored**, in both directions, so that the protocol can grow without breaking either side.

A minimal *Model* is then about as long as this:

```py
import json
import os

commands = os.fdopen(int(os.environ["MUSIBOT_IPC_COMMAND_FD"]), "r")
results = os.fdopen(int(os.environ["MUSIBOT_IPC_RESULT_FD"]), "w")
pages_dir = os.environ["MUSIBOT_PAGES_DIR"]


def send(message):
    results.write(json.dumps(message) + "\n")
    results.flush()


send({
    "type": "ready",
    "ipc_version": 1,
    "model": {
        "name": "hello-model",
        "version": "1.0.0",
        "signature": {"input": ["image.jpg"], "output": ["transcription.musicxml"]},
        "supports_batching": False,
    },
})

for line in commands:
    command = json.loads(line)

    if command["type"] == "shutdown":
        break

    if command["type"] == "execute":
        page_dir = os.path.join(pages_dir, command["page"])
        print(f"transcribing {command['page']}")  # ends up in the pipeline log
        try:
            with open(os.path.join(page_dir, "transcription.musicxml"), "w") as file:
                file.write("<score-partwise/>")
            send({"type": "completed", "execution_id": command["execution_id"]})
        except Exception as exception:
            send({
                "type": "failed",
                "execution_id": command["execution_id"],
                "error": str(exception),
            })
```


## Open questions

- **Detecting what changed** — the *Worker Head* uploads the files a command created or changed, but the detection mechanism (modification time against content hash) and whether *deletions* propagate are unspecified. See [Rough edges](rough-edges.md).
- **Per-model timeouts** — a *Model* that hangs currently ties up its *Worker* until the *Pipeline Execution* times out from above. A watchdog on the head side would bound this.
- **Weights and warm-up** — nothing in the protocol says when a *Model* may load its weights. Doing it before `ready` is the obvious choice, and delays announcement rather than delaying work, but a model with several large variants may want something more gradual.
