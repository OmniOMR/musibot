# Adding models

A *Model* is where the actual recognition happens: it reads *Files* out of a *Musicorpus Page* and writes *Files* back into it. This document is the guide to writing one and getting it running. [Worker IPC](worker-ipc.md) is the contract it implements, message by message, and [hello-model](../components/models/hello-model/) is a complete worked example that transcribes nothing — read either when this page is not specific enough.

The example built up here is a staff-level transcription model: it takes the image of one staff and produces the MusicXML for it. That is the same `staff-transcriptor` that the pipeline in [Writing pipelines](writing-pipelines.md) invokes.


## What a Model is, from your side

A program. Not a plugin, not a subclass — a program that a *Worker Head* starts as a subprocess and then talks to.

It reads commands as JSON lines from one file descriptor, writes results as JSON lines to another, and reads and writes ordinary files in a directory. That is the whole of it. A *Model* imports nothing from Musibot, knows nothing of RabbitMQ, MinIO, *Pipelines* or *Users*, and carries no Musibot dependency at all — [hello-model](../components/models/hello-model/) has no dependencies whatsoever.

What you get in exchange for that narrowness is that a *Model* brings **its own python version, its own dependencies and its own weights**. Nothing has to be reconciled with the rest of Musibot, because nothing is shared with it. A model pinned to python 3.10 runs fine under a *Worker Head* that requires 3.11.

> **Note:** Descriptor passing is POSIX-only. You can write a *Model* on any platform, but it has to reach Linux (or WSL) before a *Worker Head* can run it.


## The shape of every Model

Three environment variables are handed over at startup, and opening them is the whole of the setup:

| Variable | Meaning |
| --- | --- |
| `MUSIBOT_IPC_COMMAND_FD` | The descriptor to **read** commands from. |
| `MUSIBOT_IPC_RESULT_FD` | The descriptor to **write** results to. |
| `MUSIBOT_PAGES_DIR` | The directory holding the *Musicorpus Page* folders. |

Then: say `ready` once, and serve commands in a plain loop until told to stop.

```py
import json
import os
from pathlib import Path

IPC_VERSION = 1

commands = os.fdopen(int(os.environ["MUSIBOT_IPC_COMMAND_FD"]), "r")
results = os.fdopen(int(os.environ["MUSIBOT_IPC_RESULT_FD"]), "w")
pages_dir = Path(os.environ["MUSIBOT_PAGES_DIR"])


def send(message):
    results.write(json.dumps(message) + "\n")
    results.flush()  # a pipe is block-buffered; without this the head waits forever


send({
    "type": "ready",
    "ipc_version": IPC_VERSION,
    "model": {
        "name": "staff-transcriptor",
        "version": "2026-07-22",
        "signature": {
            "input": ["Staves/{s}/image.jpg"],
            "output": ["Staves/{s}/transcription.musicxml"],
        },
        "supports_batching": False,
    },
})

for line in commands:
    command = json.loads(line)

    if command["type"] == "shutdown":
        break
    if command["type"] != "execute":
        continue  # unknown types are ignored in both directions, so the protocol can grow

    try:
        transcribe(pages_dir / command["page"], command["input"])
    except Exception as exception:
        send({
            "type": "failed",
            "execution_id": command["execution_id"],
            "error": str(exception),
        })
    else:
        send({"type": "completed", "execution_id": command["execution_id"]})
```

Only one command is ever in flight — the *Worker Head* sends nothing further until this one is reported — so a *Model* may be written as exactly this loop, with no concurrency anywhere.

Reading EOF on the command pipe means the same thing as `shutdown`, which is what a *Worker Head* that died looks like from here. Iterating the file, as above, handles both.


## Declaring what it reads and writes

The `signature` in the `ready` message is the part worth thinking about, and it is not a list of *Files*. It describes **which sets of *Files* are admissible**, so that it is true of every page rather than of one:

```json
"signature": {
  "input": ["Staves/{s}/image.jpg"],
  "output": ["Staves/{s}/transcription.musicxml"]
}
```

`{s}` is a *slot*: it stands for one subdivision instance, and using the same name on both sides says that the transcription lands beside the image it came from. [Signatures](signatures.md) is the full reference — the short version is that a whole path segment may be `{}` or `{name}` for one instance, `{*}` or `{*name}` for all of them, and a trailing `?` marks an entry optional.

A *Signature* is what makes your *Model* usable by someone who has never read your code. It is announced through [Discovery](discovery.md), appears in `GET /pipelines`, and is what tells a *User* to send `Staves/7/image.jpg` rather than `image.jpg`. A *Model* with no *Signature* is a *Model* nobody can call.


### Which Files you actually get

The patterns are the declaration. The concrete paths arrive with each command, in `input`:

```json
{ "type": "execute", "execution_id": "e7c1", "page": "7Kf2mP9xLwQa",
  "input": ["Staves/7/image.jpg"], "parameters": {} }
```

So a *Model* never expands its own patterns. It reads the paths it was handed, and derives its output from them:

```py
def transcribe(page_dir, input_files):
    [staff_image] = input_files  # one staff per execution — that is what `{s}` declares

    musicxml = my_model.predict(page_dir / staff_image)

    output = (page_dir / staff_image).parent / "transcription.musicxml"
    output.write_text(musicxml, encoding="utf-8")
```

Those are the only *Files* staged for you. The *Worker Head* downloads exactly the `input` list and nothing else, so a *File* your *Signature* does not declare will not be there — which is why an optional input has to be declared with `?` rather than read opportunistically.

Confine yourself to the page folders named in the command you are currently executing. Paths that escape a page folder are rejected by the *Worker Head*.


### One instance at a time, or all of them

A staff model could declare `Staves/{s}/image.jpg` — one staff per execution — or `Staves/{*s}/image.jpg` — every staff of a page at once. The rule:

> Use `{s}` when your *Model* treats instances **independently**, and set `supports_batching` so the *Worker Head* groups them for you. Use `{*}` only when your *Model* must see the **whole set** to do its work.

Transcribing staff 7 does not depend on staff 8, so the staff transcriptor takes `{s}`. A model that joins staff transcriptions into systems does need to see them all, and `{*}` is the only honest thing it can say.

This is a correctness rule and not a matter of taste. A batch reports one `completed` or `failed` per `execution_id`, so with `{s}` the unit of work and the unit of reporting are the same thing, and one unreadable staff fails one staff. With `{*s}`, a single bad staff inside a twelve-staff execution has no message to be reported in — you would have to fail all twelve or silently skip one.

> **Not yet implemented:** the *Worker Head* reads and announces `supports_batching`, but never issues `execute-batch` — every execution is sent as its own `execute` command. A batching *Model* therefore works correctly today, just without the throughput it will get later. Declaring `{s}` is right either way.


### What is checked

Little, and in two places. The `api` service refuses an input list that does not fit your *Signature* with a `400`, so twelve staves handed to a `{s}` *Model* never reach you. And the *Worker Head* **fails an execution whose *Model* reported success without writing an output the *Signature* promises outright** — the slot-free, non-optional entries. Writing output to the wrong path is the commonest way to get a *Model* wrong, and it would otherwise surface as a *Pipeline* that succeeds and produces nothing.

*Files* you write that the *Signature* does not describe are kept and uploaded anyway, and logged. Nothing is thrown away.

Beyond that, a *Signature* is a declaration rather than a contract enforced on every hop. If your real expectations are narrower than anything expressible in one — a JPEG of at least some resolution, say — declare the wider *Signature* and report a plain `failed` for input that satisfies it but not you.


## Failing an execution

Report `failed` with an `error` string rather than letting an exception take the process down. The string is propagated into the *Pipeline Execution* log and reaches a human, so it is worth writing for one: `"No staves found in the image."` beats a fragment of a traceback.

A *Model* that dies fails its work anyway — every execution in flight is reported as failed, and the *Worker Head* restarts the model and resumes taking work once it says `ready` again — but it reports nothing useful about why.


## Logging

Anything the *Model* prints to stdout or stderr is captured by the *Worker Head* as that model's log, published onto RabbitMQ attributed to the *Pipeline Execution* it belongs to, and shown to the *User* in the Web UI as it is printed. There is no logging setup to do, and no way for a stray `print` to corrupt the protocol, because the protocol is on two other descriptors:

```py
print(f"transcribing staff {staff_number}")
```

stdout is forwarded at level `info` and stderr at `warning`, which is the whole of the distinction. The *Worker Head* starts the *Model* with `PYTHONUNBUFFERED=1` so those lines arrive promptly rather than in delayed clumps. A *Model* not written in python has to arrange the equivalent.

Write for a human watching a page being read: a line naming what is being worked on is worth printing, and a line per tensor is not. There is no progress reporting in Musibot and none is coming — an execution takes a second or two, and a model that can honestly say how far along it is is the exception rather than the rule.


## Loading weights

Before sending `ready`. The *Worker Head* consumes no work from RabbitMQ and announces nothing until its model has said it, so a model that spends a minute loading weights is simply not offered work during that minute — rather than being offered work it cannot yet do. The head's `model_ready_timeout_seconds` is generous by default for exactly this reason.

Where the weights come from is your repository's business — GitHub releases, Hugging Face, or committed alongside the code. They are never committed to the Musibot monorepo.


## Packaging it

A *Model* is a pip-installable package, which is what lets it be deployed from a GitHub link without touching the Musibot repository. Nothing about the packaging is Musibot-specific:

```toml
[project]
name = "staff-transcriptor"
version = "1.0.0"
# Whatever your model needs. It may be older than the 3.11 that `core` requires:
# a Model is reached only over pipes and the filesystem.
requires-python = ">=3.10"
dependencies = ["torch", "numpy"]

[project.scripts]
staff-transcriptor = "staff_transcriptor:main"
```

A *Model* that lives in this monorepo goes in `components/models/<model-name>/` — see [that folder's README](../components/models/README.md) for the layout it follows. One that lives in its own repository is identical in every other respect.


## Running it under a Worker Head

A *Model* is never started by hand. Install it, install the [worker head](../components/worker-head/README.md), and point the head at the command that launches your model:

```bash
musibot-worker-head --model-command "/opt/models/staff-transcriptor/.venv/bin/python -m staff_transcriptor"
```

Against the [local development stack](../deploy/README.md) every other setting already defaults correctly, so that one argument is enough to have your *Model* announced and runnable. It then appears in `GET /pipelines` as an *ImplicitPipeline* — the single-*Model* pipeline Musibot offers for every *Model* it knows about — which is how you exercise it in isolation before any *Pipeline* uses it:

```py
client.process_page(
    input={"Staves/7/image.jpg": Path("staff.jpg").read_bytes()},
    pipeline=("staff-transcriptor", "2026-07-22"),
    output={"Staves/7/transcription.musicxml"},
)
```

An *ImplicitPipeline* is exactly your *Signature* and nothing more: a `{s}` *Model* processes one staff per run here, because that is what it declared. Something friendlier for *Users* — one call that transcribes a whole page — is a real *Pipeline*, written in an *Orchestrator*. See [Writing pipelines](writing-pipelines.md).

For deploying onto a real machine, including the case where your model cannot share a virtual environment with the worker head, see [Deployment](deployment.md).


## Testing it

Factor the loop into a function taking the two streams and the pages directory, as [hello-model](../components/models/hello-model/hello_model/__init__.py) does:

```py
def run(commands, results, pages_dir):
    ...
```

A test can then drive the whole IPC exchange over `io.StringIO`, with no subprocess, no pipes and no *Worker Head*: script a `ready`-then-`execute`-then-`shutdown` conversation and assert on what came back. The *Worker Head* has its own tests for descriptor passing, flushing and a model that dies, so yours do not need to repeat them.


## Versioning

Three numbers are easy to confuse here, and only two of them are Musibot's:

| Number | What it is |
| --- | --- |
| **Model version** | What a *Pipeline* pins and what [Discovery](discovery.md) announces. Musibot treats it as an opaque string and never parses it, so a date works as well as semver. Declared in `ready`. |
| **`ipc_version`** | The version of the [worker IPC contract](worker-ipc.md) you implement. One integer, `1` today, checked for exact equality — a *Model* announcing anything else is refused rather than driven on a guess. |
| **The package version** | Packaging only. Nothing in Musibot reads it. |

Keep the model version a constant in your code rather than deriving it from the installed distribution: what a *Pipeline* pinned should not change because the model was repackaged.


## Things that go wrong

- **Forgetting to flush.** A pipe is block-buffered, so an unflushed message is not late — it is invisible, and the *Worker Head* waits forever. This is the single easiest way to get a *Model* wrong.
- **Writing the protocol to stdout.** It goes on the two descriptors named in the environment. stdout is your log, and is meant to be printed to.
- **Writing output where the *Signature* does not promise it.** The *Worker Head* fails the execution and says so, rather than letting it look like a success that produced nothing.
- **Declaring `{*}` for work that is really independent.** It costs you per-instance failure reporting, and the batching you would otherwise get for free.
- **Loading weights after `ready`.** The *Worker* is offered work it cannot yet do.
- **Reading a *File* the *Signature* does not declare.** It was never staged, so it is not there.
