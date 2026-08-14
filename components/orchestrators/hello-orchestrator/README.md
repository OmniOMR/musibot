# hello-orchestrator

An *Orchestrator* that recognises nothing. It exists so that the *Pipeline* half of Musibot can be exercised end to end without any real recognition in the way — and so that there is one worked example of the [Orchestrator Head API](../../orchestrator-head/README.md) to read. It is the counterpart of [hello-model](../../models/hello-model/README.md) on the other side of the system.


## What it provides

| | |
| --- | --- |
| Orchestrator name | `hello-orchestrator` |
| Pipeline | `hello-pipeline` `1.0.0` |
| Input | `image.jpg` |
| Output | `layout.json`, `transcription.musicxml` |
| Models it runs | `hello-model` `1.0.0` |

The *Pipeline* does the three things every real *Pipeline* does, and nothing else:

1. **Runs a *Model*.** `hello-model`, which writes `transcription.musicxml` into the page.
2. **Reads what that *Model* produced,** and says in the log how many bytes the model read. That number is one only the *Model* could have known, so seeing it in the *Pipeline's* log is what proves a *Pipeline* can read a *Model's* output rather than merely trigger it.
3. **Writes a *File* of its own.** A `layout.json` holding one staff, inset 20 pixels from every edge of the image. The staff is made up; the reading and writing of it is not.

`transcription.musicxml` appears in the output half of the *Signature* even though this *Pipeline* never writes it — the *Model* it runs does, into the same page, and a *Signature* describes what an execution leaves behind rather than who put it there.


## What it demonstrates

**A *Pipeline* is parametrized, not hard-coded.** Which *Model* version to run and how wide the margin is are constructor arguments, fed from this *Orchestrator's* own settings. That is the mechanism the real pipelines need: one implementation registered twice, once pinning the *Model* snapshot in production and once pinning the one being developed.

**An *Orchestrator* may bring its own dependencies.** This one has Pillow, to read the size of the image. The *Orchestrator Head* does not have it and does not want it: to Musibot a *File* is opaque bytes, and knowing that some of them are a JPEG is a *Pipeline's* business.

**A *Pipeline* is testable as ordinary python.** Its tests use `PipelineRunner` from the head's `testing` module — no broker, no object storage, no *Model*, and no async test framework.


## Configuration

Beyond the shared RabbitMQ, MinIO and logging blocks (see [service configuration](../../../docs/service-configuration.md)):

| Setting | Default | Meaning |
| --- | --- | --- |
| `hello_model_version` | `1.0.0` | Which snapshot of `hello-model` the *Pipeline* pins. |
| `staff_margin` | `20` | How far the made-up staff sits from each edge, in pixels. |
| `max_concurrent_executions` | `4` | From the head — how many executions run at once. |


## Development

```bash
cd components/orchestrators/hello-orchestrator
python3 -m venv .venv
.venv/bin/pip install -e ../../core -e ../../orchestrator-head -e '.[dev]'
```


## Running it

Against the [local development stack](../../../deploy/README.md) it takes no arguments at all — every default already points there:

```bash
.venv/bin/musibot-hello-orchestrator
```

To see the whole thing work, four processes are needed: the stack, the `api` service, a *Worker* running `hello-model`, and this.

```bash
cd deploy && docker compose up -d                                   # RabbitMQ and MinIO
components/api/.venv/bin/musibot-api                                # the api service
components/worker-head/.venv/bin/musibot-worker-head \              # the Worker
    --model-command "../models/hello-model/.venv/bin/python -m hello_model"
components/orchestrators/hello-orchestrator/.venv/bin/musibot-hello-orchestrator
```

`hello-pipeline` then appears in `GET /pipelines` beside the *ImplicitPipeline* of `hello-model`, and running it against a page holding an `image.jpg` produces both output *Files* and a log a *User* can watch as it happens.

Overriding a setting is the ordinary way, and is how the two-registration pattern is exercised:

```bash
.venv/bin/musibot-hello-orchestrator --hello-model-version 1.0.0 --staff-margin 5
```


## Testing

```bash
.venv/bin/python -m pytest
.venv/bin/python -m ruff check .
.venv/bin/python -m ruff format --check .
.venv/bin/python -m mypy
```


## Versioning

The *Pipeline's* version is what a *User* pins, and it is a domain concept declared in the code — `hello-pipeline` `1.0.0` — rather than derived from repository history. The package version in `pyproject.toml` is packaging only and nothing in Musibot reads it. This follows the same rule as `models`; see [Versioning and releases](../../../docs/versioning-and-releases.md).
