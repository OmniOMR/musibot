# pmcg-orchestrator

The *Orchestrator* holding the *Pipelines* of the Prague Music Computing Group (PMCG) and its partners, the OmniOMR project's among them. Two of them, and they are the two things a *User* arrives with:

- **`mzk-page`** — a page scan in, a page-level MusicXML file out.
- **`mzk-staff`** — one staff crop in, its transcription out.

Both are named in [the Web UI](../../web-ui/src/pipelines.ts), which offers them as its two defaults, so their names and versions are part of what this deployment promises rather than an internal detail.

This is the *Pipeline* Musibot exists to run. Everything else that ships in this repository — `hello-model`, `hello-orchestrator` — is plumbing to exercise the path this takes.


## What `mzk-page` does

| | |
| --- | --- |
| Orchestrator name | `pmcg` |
| Pipeline | `mzk-page` `2` |
| Implementation | `PageFromStaffPipelineV2`, around dvorak-ola and ayce-long |
| Input | `image.jpg` |
| Output | `layout.json`, `Staves/{*}/image.jpg`, `Staves/{*}/transcription.musicxml`, `transcription.musicxml` |
| Models it runs | a layout model, then a staff transcription model once per staff |

Four steps, and a *User* watching the page is told about each as it happens:

1. **Find the staves.** A layout *Model* — [dvorak-ola](../../models/dvorak-ola/README.md) — writes `layout.json`, a COCO document of page-structure boxes. This reads its `staff`, `system` and `grandstaff` boxes and groups the staves into instruments, following each instrument from system to system down the page.
2. **Cut the page up.** One JPEG crop per staff, written to `Staves/<n>/image.jpg`, with a margin proportional to the staff's own height.
3. **Transcribe each staff.** A transcription *Model* — [zeus](../../models/zeus/README.md) — runs once per staff, all of them dispatched at once, each producing `Staves/<n>/transcription.musicxml`.
4. **Glue them together.** One `score-partwise` document with a `<part>` per instrument, each holding that instrument's measures system after system, with an explicit system break where each system begins.

Steps 1 and 3 are *Models*, pinned in the source where the *Pipeline* is registered. Steps 2 and 4 are this *Pipeline's* own code, and are the parts that will move into a Musicorpus library when one exists — turning a page and its layout into subdivision crops is true of the format rather than of this deployment. Until then this is the only *Pipeline* that slices, so it is developed here.

The intermediate *Files* stay in the page deliberately. They are what somebody looks at when the result is wrong, and a *MusicorpusPage* is discarded a few minutes later anyway.


## What version 2 does, and what it still does naively

Both of the steps this *Pipeline* owns are worth stating plainly, because each is a reason the version number will move:

**The gluing reads the page as instruments.** The `system` boxes say which staves sound at once, and the `grandstaff` boxes which two of them are one instrument. Each instrument becomes a `<part>`, and a grand staff's two staves are zipped into one two-staff part. Staves sharing a system are padded to the same number of measures with marked `Padding measure`s, an instrument missing from a system is written there as hidden measure rests, and the clef, key and time signature a staff does not print are carried over from that instrument's preceding staff. A page whose layout has no `system` boxes is read as one system, so its staves become that many instruments playing at once.

**The slicing is a rectangle.** No deskewing, no straightening, no normalising of staff height. A transcription model that wants any of those should say so, and then it belongs in step 2 as a step of its own rather than smuggled into the crop.

**Reading order is down the page and then across.** A page laid out in two columns would have its staves interleaved. Finding the columns first is real work and is not done.

**One staff failing does not fail the page.** A scan of a real book has stains, cropped systems, and pages the detector was too generous about, so returning eleven staves of twelve is far more useful than returning an error. A failed staff is said in the log, and keeps its place in its instrument's part, carrying the words `Cannot transcribe staff 7` — said in the document, because an empty measure is otherwise indistinguishable from a staff the *Model* read as silence. A page where *every* staff failed does fail.


## What `mzk-staff` does

It runs the transcription *Model* on the *File* it was given, and nothing else — the *User* has already done the cutting. Step for step that is what the *Model's* own *ImplicitPipeline* does, and it exists anyway for the name: an *ImplicitPipeline* is called after the *Model* behind it, so it is `ayce-long 2026-08-03-192253-final` today and something else the day a better snapshot is deployed. `mzk-staff` `1` does not move when the snapshot does, so the *Web UI* can offer it and a *User* can pin it.

Its *Signature* is the *Model's* own — `Staves/{s}/image.jpg` in, `Staves/{s}/transcription.musicxml` out — which is also what tells the *Web UI* to upload a staff crop to `Staves/1/image.jpg` rather than to `image.jpg`.


## Pipeline versions are a contract

A *Pipeline's* name and version are a promise to the *User* about how it behaves, not a stamp on one particular implementation. So everything that decides that behaviour is in the source, and nothing of it is configuration: which implementation, which *Models* it runs, the constants it slices with, and the name and version it is announced under. `registered_pipelines()` in [`pmcg_orchestrator/__init__.py`](pmcg_orchestrator/__init__.py) is the whole contract, one line per published *Pipeline*.

Changing any of it is a change to this program and a re-deployment. **Bump a pipeline's version whenever the same input would come out noticeably different** — a new *Model* snapshot, a change to the slicing, a change to the gluing. A bug fix that makes a *Pipeline* do what it always claimed to need not, and the old and new versions of a *Pipeline* are both registered in the same process for as long as anyone may be pinning the old one. They share whatever code they can.


## Developing a pipeline

A new *Pipeline*, or a new version of an existing one, is registered in `registered_pipelines()` like any other, under a version with a **`-dev` suffix** — `mzk-page` `3-dev`. The suffix is what a *User* reading the listing of a shared instance sees, and it tells them this is work in progress rather than a release. When it is finished, the registration is renamed to its real version.

To run it without disturbing anything, start the *Orchestrator* announcing that *Pipeline* alone:

```bash
.venv/bin/musibot-pmcg-orchestrator --only-pipelines mzk-page@3-dev
```

Every other *Pipeline* is left to the instances already serving it. That matters against a shared Musibot: an *Orchestrator* announcing a published *Pipeline* joins that *Pipeline's* work queue as one more competing consumer, so a laptop running unfinished code under `mzk-page@2` would quietly take production work. Naming a *Pipeline* that is not registered stops the process at startup.


## Configuration

Beyond the shared RabbitMQ, MinIO and logging blocks (see [service configuration](../../../docs/service-configuration.md)), only which *Pipelines* to announce:

| Setting | Default | Meaning |
| --- | --- | --- |
| `only_pipelines` | *(all)* | Announce only these *Pipelines*, each written `name@version`. Repeat the flag for several; in the environment it is a JSON list, `MUSIBOT_ONLY_PIPELINES='["mzk-page@3-dev"]'`. For development — see above. |
| `max_concurrent_executions` | `4` | From the head — how many pages this process reads at once. |


## Development

```bash
cd components/orchestrators/pmcg-orchestrator
python3 -m venv .venv
.venv/bin/pip install -e ../../core -e ../../orchestrator-head -e '.[dev]'
```

Running it needs the [local development stack](../../../deploy/README.md), the `api` service, and a *Worker* for each of the two *Models* — which is the point at which a laptop is running the whole system:

```bash
.venv/bin/musibot-pmcg-orchestrator
```


## Testing

`PipelineRunner` from the head's `testing` module stands in for the broker, object storage and the *Models*, so the tests are ordinary synchronous python and need none of Musibot running. The fake staff model writes real MusicXML and the fake layout model writes a real COCO document, so what is exercised is the parsing, the slicing arithmetic and the concatenation rather than a mock agreeing with itself.

```bash
.venv/bin/python -m pytest
.venv/bin/python -m ruff check .
.venv/bin/python -m ruff format --check .
.venv/bin/python -m mypy
```


## Versioning

Each *Pipeline's* name and version is what a *User* pins, and both are constants in the source — see [above](#pipeline-versions-are-a-contract). The package version in `pyproject.toml` is packaging only and nothing in Musibot reads it. See [Versioning and releases](../../../docs/versioning-and-releases.md).
