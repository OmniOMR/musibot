# omniomr-orchestrator

The *Orchestrator* holding the OmniOMR project's *Pipelines*. Two of them, and they are the two things a *User* arrives with:

- **`mzk-page`** — a page scan in, a page-level MusicXML file out.
- **`mzk-staff`** — one staff crop in, its transcription out.

Both are named in [the Web UI](../../web-ui/src/pipelines.ts), which offers them as its two defaults, so their names and versions are part of what this deployment promises rather than an internal detail.

This is the *Pipeline* Musibot exists to run. Everything else that ships in this repository — `hello-model`, `hello-orchestrator` — is plumbing to exercise the path this takes.


## What `mzk-page` does

| | |
| --- | --- |
| Orchestrator name | `omniomr` |
| Pipeline | `mzk-page` `1` (both are settings — see below) |
| Input | `image.jpg` |
| Output | `layout.json`, `Staves/{*}/image.jpg`, `Staves/{*}/transcription.musicxml`, `transcription.musicxml` |
| Models it runs | a layout model, then a staff transcription model once per staff |

Four steps, and a *User* watching the page is told about each as it happens:

1. **Find the staves.** A layout *Model* — [dvorak-ola](../../models/dvorak-ola/README.md) — writes `layout.json`, a COCO document of page-structure boxes. This reads the `staff` boxes out of it, in reading order.
2. **Cut the page up.** One JPEG crop per staff, written to `Staves/<n>/image.jpg`, with a margin proportional to the staff's own height.
3. **Transcribe each staff.** A transcription *Model* — [zeus](../../models/zeus/README.md) — runs once per staff, all of them dispatched at once, each producing `Staves/<n>/transcription.musicxml`.
4. **Glue them together.** One `score-partwise` document holding every staff's measures in a single `<part>`, one after another, with an explicit system break where each staff begins.

Steps 1 and 3 are *Models* and are named by configuration. Steps 2 and 4 are this *Pipeline's* own code, and are the parts that will move into a Musicorpus library when one exists — turning a page and its layout into subdivision crops is true of the format rather than of this deployment. Until then this is the only *Pipeline* that slices, so it is developed here.

The intermediate *Files* stay in the page deliberately. They are what somebody looks at when the result is wrong, and a *MusicorpusPage* is discarded a few minutes later anyway.


## What version 1 does naively

Both of the steps this *Pipeline* owns are the simplest thing that can work. They are worth stating plainly, because each is a reason the version number will move:

**The concatenation reads the page as one instrument.** Every staff's measures go into one `<part>`, one staff after another, with a system break where each begins — which is what a page of solo music is, and it survives staves disagreeing about how many measures they have. What it cannot express is genuine polyphony: a piano system's two staves become two consecutive systems rather than one grand staff, and a four-part system becomes four systems. Doing better needs the `system` and `grandstaff` boxes the layout model already reports and this does not yet read. That is the obvious next version.

(The first attempt gave each staff its own `<part>`, which is worse in the common case: it reads a solo piece as an N-instrument score whose parts sound at once, so nine staves of one melody become nine simultaneous melodies.)

**The slicing is a rectangle.** No deskewing, no straightening, no normalising of staff height. A transcription model that wants any of those should say so, and then it belongs in step 2 as a step of its own rather than smuggled into the crop.

**Reading order is down the page and then across.** A page laid out in two columns would have its staves interleaved. Finding the columns first is real work and is not done.

**One staff failing does not fail the page.** A scan of a real book has stains, cropped systems, and pages the detector was too generous about, so returning eleven staves of twelve is far more useful than returning an error. A failed staff is said in the log, and takes up a system of its own in the score carrying the words `Staff 7 could not be transcribed` — said in the document, because an empty measure is otherwise indistinguishable from a staff the *Model* read as silence. A page where *every* staff failed does fail.


## What `mzk-staff` does

It runs the transcription *Model* on the *File* it was given, and nothing else — the *User* has already done the cutting. Step for step that is what the *Model's* own *ImplicitPipeline* does, and it exists anyway for the name: an *ImplicitPipeline* is called after the *Model* behind it, so it is `ayce-long 2026-08-03-192253-final` today and something else the day a better snapshot is deployed. `mzk-staff` `1` does not move when the snapshot does, so the *Web UI* can offer it and a *User* can pin it.

Its *Signature* is the *Model's* own — `Staves/{s}/image.jpg` in, `Staves/{s}/transcription.musicxml` out — which is also what tells the *Web UI* to upload a staff crop to `Staves/1/image.jpg` rather than to `image.jpg`.


## Development pipelines

Every *Pipeline's* name and version is a setting, so the development *Pipeline* is **this same program started differently** rather than a second implementation:

```bash
# what production runs
musibot-omniomr-orchestrator

# the next version, against a newer snapshot, beside it
musibot-omniomr-orchestrator \
    --page-pipeline-name mzk-page-dev --page-pipeline-version 2 \
    --staff-pipeline-name mzk-staff-dev --staff-pipeline-version 2 \
    --staff-model 'ayce-long@2026-08-14-...'
```

Both may run against one Musibot at the same time. They announce different *Pipelines*, so a *User* chooses by name and neither takes the other's work. Under systemd that is two instances of `musibot-orchestrator@` with two environment files — see [Deploying onto a VM](../../../docs/deploying-to-a-vm.md#8-an-orchestrator).

**Bump a pipeline's version whenever the same input would come out different.** A new *Model* snapshot, a change to the slicing, a change to the concatenation. That is what a *User* pinning a version is protecting themselves against, and it is the only reason the number exists.


## Configuration

Beyond the shared RabbitMQ, MinIO and logging blocks (see [service configuration](../../../docs/service-configuration.md)):

| Setting | Default | Meaning |
| --- | --- | --- |
| `page_pipeline_name` | `mzk-page` | What the page-level *Pipeline* is announced as. |
| `page_pipeline_version` | `1` | And at what version. |
| `staff_pipeline_name` | `mzk-staff` | The staff-level one. |
| `staff_pipeline_version` | `1` | And at what version. |
| `layout_model` | `dvorak-ola@2.0-2025-03-09` | The *Model* that finds the staves. |
| `staff_model` | `ayce-long@2026-08-03-192253-final` | The *Model* that transcribes one staff. |
| `staff_padding_ratio` | `0.9` | Margin added around each staff when cutting it out, as a fraction of that staff's height. |
| `layout_confidence` | *(unset)* | Passed to the layout *Model* as its `confidence`. Unset leaves that model's own default alone. |
| `max_concurrent_executions` | `4` | From the head — how many pages this process reads at once. |

A *Model* is written `name@version`, the spelling routing keys use, and a malformed one stops the process at startup rather than becoming a *Pipeline* that announces itself and then times out every execution.

**The two model defaults are the development stack's current snapshots**, so that this starts with no arguments against it, as every other Musibot service does. A deployment pins both explicitly: a superseded snapshot is exactly what a default quietly goes on pointing at.

The margin is a *fraction of the staff's height* rather than a pixel count so that it means the same thing on a 300dpi scan and a 600dpi one — the margin scales with the thing whose size the resolution changes.


## Development

```bash
cd components/orchestrators/omniomr-orchestrator
python3 -m venv .venv
.venv/bin/pip install -e ../../core -e ../../orchestrator-head -e '.[dev]'
```

Running it needs the [local development stack](../../../deploy/README.md), the `api` service, and a *Worker* for each of the two *Models* — which is the point at which a laptop is running the whole system:

```bash
.venv/bin/musibot-omniomr-orchestrator
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

Each *Pipeline's* name and version is what a *User* pins, and both are configuration here rather than constants — which is unusual, and is what makes a development deployment possible without a second codebase. The package version in `pyproject.toml` is packaging only and nothing in Musibot reads it. See [Versioning and releases](../../../docs/versioning-and-releases.md).
