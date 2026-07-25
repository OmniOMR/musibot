# hello-model

A *Model* that transcribes nothing. It exists so that the rest of Musibot can be exercised end to end without any machine learning in the way — and so that there is one worked example of the [worker IPC contract](../../../docs/worker-ipc.md) to read.


## What it does

| | |
| --- | --- |
| Name and version | `hello-model` `1.0.0` |
| Input | `image.jpg` |
| Output | `transcription.musicxml` |
| Batching | No |

It reads `image.jpg` from the page folder and writes a well-formed, one-measure MusicXML file whose lyric reads `Hello World! (12345 bytes)`. The byte count is the useful part: it is what shows the *File* actually travelled from the *User* through MinIO into the *Worker Head's* local mirror before the *Model* ran. Nothing about the image is examined — it is not even required to be a JPEG.

An execution fails if `image.jpg` is missing, which is the failure path a *Pipeline Execution* surfaces to the *User*.


## What it deliberately is not

It imports nothing from Musibot and has **no dependencies at all**, which is what a *Model* is allowed to look like. It declares `requires-python = ">=3.9"` — below the 3.11 that `core` and the *Worker Head* need — to make the point concrete: a *Model* is reached only over pipes and the filesystem, so it may run on a python the rest of the system could not.


## Weights

None. A real model keeps them in its own repository (GitHub releases, Hugging Face, or baked in); see [../README.md](../README.md).


## Development

```bash
cd components/models/hello-model
python3 -m venv .venv
.venv/bin/pip install -e '.[dev]'
```


## Running it

A *Model* is never started by hand — a *Worker Head* launches it and hands it the two file descriptors it talks over. See [deployment](../../../docs/deployment.md); the short version is that the worker head is pointed at this command:

```bash
musibot-worker-head --model-command ".venv/bin/python -m hello_model"
```

Because this model has no dependencies to conflict with, it can share the worker head's virtual environment — the common, simplest case of the two described in [deployment](../../../docs/deployment.md).


## Testing

Unit tests drive the IPC loop over in-memory streams instead of real pipes, so they need neither a *Worker Head* nor a subprocess.

```bash
.venv/bin/python -m pytest
.venv/bin/python -m ruff check .
.venv/bin/python -m ruff format --check .
.venv/bin/python -m mypy
```
