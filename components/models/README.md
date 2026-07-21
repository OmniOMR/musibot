# models

Most Musibot models live in **their own repositories** and only implement the worker-head IPC interface; this folder holds the few **reference models** that ship inside the Musibot monorepo. Either way a model is fully isolated: its own dependencies, its own python version, its own weights.


## What a model provides

A model is a subprocess that speaks the worker head's IPC contract (instructions over stdin and the filesystem). It is pip-installable — models in their own repositories are installed via a GitHub link — so deploying one never modifies the Musibot repository.


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

Clone or install the model, create a venv on the required python version, `pip install` the model plus the `worker-head`, and start the worker head against RabbitMQ + MinIO (see `docs/deployment.md`). "Deploy to production" then means pointing a pipeline at this model version.


## Testing

Per-model unit tests. Heavier MusicXML-level, retrieval, and end-to-end pipeline metrics run on a separate benchmarking rig (see `docs/who-are-the-users.md` §2), not in this repo's CI.


## Versioning

Model version is a first-class domain concept — it is what pipelines pin and what a deployment selects.
