# models

Some Musibot models ship inside this monorepo (this folder) and others live in their own repositories; either way a model only implements the worker-head IPC interface. And either way a model is fully isolated: its own dependencies, its own python version, its own weights.


## What a model provides

A model is a subprocess that speaks the worker head's IPC contract (instructions over a dedicated pair of pipes and the filesystem). It is pip-installable — a model in its own repository is installed via a GitHub link — so deploying one never modifies the Musibot repository.


## Models in this folder

- **[hello-model](hello-model/)** — transcribes nothing; reads `image.jpg` and writes a fixed `transcription.musicxml`. It is the worked example of the [worker IPC contract](../../docs/worker-ipc.md) and what the rest of Musibot is exercised against without any machine learning in the way.
- **[zeus](zeus/)** — *no code here.* Zeus lives in [its own repository](https://github.com/OmniOMR/zeus); this folder holds how our instance deploys it — the environment file its systemd unit reads, and the steps that produce it.

That second entry is a different kind of thing from the first, and the difference is worth stating. A model's *code* is here only when it ships in this monorepo. A model's *deployment* is here whenever we are the ones running it, external repository or not: Musibot's design keeps deploying a model from touching this repository, and that stays true — Zeus is installed from a git link and reached only over the IPC — but the deployment of the one instance we operate has to be written down somewhere, and one place beats one per model repository. The division is that a model's own repository documents deploying it in general, while this folder documents deploying it onto our VM under systemd.


## Layout (per reference model in this folder)

```
models/<model-name>/
  pyproject.toml        # deps for THIS model only
  <model-name>/         # model code implementing the IPC contract
  tests/
  README.md             # what it does, input/output, weights source
```


## Model weights

Weights are the responsibility of the model's own repository — GitHub releases, Hugging Face, or baked into the repo, depending on the model. They are never committed to the Musibot monorepo.


## Deployment

Clone or install the model, create a venv on the required python version, `pip install` the model plus the `worker-head`, and start the worker head against RabbitMQ + MinIO (see `docs/deployment.md`). A model that cannot share a venv with the worker head — one needing a python older than 3.11, or with conflicting pins — gets a venv of its own and is launched by path across the IPC boundary. "Deploy to production" then means pointing a pipeline at this model version.


## Testing

Per-model unit tests. Heavier MusicXML-level, retrieval, and end-to-end pipeline metrics run on a separate benchmarking rig (see `docs/who-are-the-users.md` §2), not in this repo's CI.


## Versioning

Model version is a first-class domain concept — it is what pipelines pin and what a deployment selects.

A *Model* author is handling three numbers that are easy to confuse, so it is worth naming them apart:

| Number | What it is | Where it lives |
| --- | --- | --- |
| **Model version** | The domain concept above: what a *Pipeline* pins and what [discovery](../../docs/discovery.md) announces. Musibot treats it as an opaque identifier and never parses it, so semver is a convention here rather than a requirement — a date works just as well. | Declared in the model's `ready` message. |
| **`ipc_version`** | The version of the [worker IPC contract](../../docs/worker-ipc.md) the model implements. A single integer, `1` today, checked by the *Worker Head* for exact equality — a model announcing anything else is refused. | Declared in the same `ready` message. |
| **The python package version** | Packaging only, for whoever `pip install`s the model. Nothing in Musibot reads it. | The model's `pyproject.toml`. |

The first two are deliberately independent of the third: [hello-model](hello-model/) keeps its announced `MODEL_VERSION` as its own constant rather than deriving it from the installed distribution, because what a *Pipeline* pinned should not change just because the model was repackaged. See [the protocol version](../../docs/worker-ipc.md#the-protocol-version) for how `ipc_version` differs from the `worker-head` component's own semver.
