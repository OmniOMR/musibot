# pmcg-orchestrator

The *Orchestrator* holding the *Pipelines* of the Prague Music Computing Group (PMCG) and its partners, the OmniOMR project's among them. These are the *Pipelines* Musibot exists to run; everything else that ships in this repository — `hello-model`, `hello-orchestrator` — is plumbing to exercise the path they take.


## Published pipelines

| Pipeline | What it does | Implementation | Models |
| --- | --- | --- | --- |
| `mzk-page` `1` | a page scan in, a page-level MusicXML file out, as one instrument | `PageFromStaffPipelineV1` | dvorak-ola, ayce-long |
| `mzk-page` `2` | a page scan in, a page-level MusicXML file out, a part per instrument | `PageFromStaffPipelineV2` | dvorak-ola, ayce-long |
| `mzk-staff` `1` | staff crops in, their transcriptions out | `StavesFromStaffPipeline` | ayce-long |
| `pmcg-slice` `1` | a page and its `layout.json` in, a crop per staff out | `SlicePipelineV1` | — |
| `pmcg-glue` `1` | a `layout.json` and staff transcriptions in, a page as one instrument out | `GluePipelineV1` | — |
| `pmcg-glue` `2` | a `layout.json` and staff transcriptions in, a page as a part per instrument out | `GluePipelineV2` | — |

The *Models* are pinned exactly: `dvorak-ola` `2.0-2025-03-09` finds the staves, and `ayce-long` `2026-08-03-192253-final`, a [Zeus](../../models/zeus/README.md) snapshot, transcribes them. The *Orchestrator* announces itself as `pmcg`.

`mzk-page` `1` and `mzk-staff` `1` are named in [the Web UI](../../web-ui/src/pipelines.ts), which offers them as its two defaults, so their names and versions are part of what this deployment promises rather than an internal detail. The `mzk-` *Pipelines* are named after the Moravian Library (MZK), whose work they were built for, while the implementations behind them are not particular to it: the same class can be published again around other *Models* — a commercial transcription model, say — under another name.

`pmcg-slice`, `mzk-staff` and `pmcg-glue` are the steps of `mzk-page` one by one, for a *User* who wants a person in the loop — correcting the layout before anything is transcribed, for instance. **Run in that order on the same page, they produce exactly the file `mzk-page` would have written**, of the same version as the `pmcg-glue` used; see [Running the steps by hand](#running-the-steps-by-hand).


## Pipeline versions are a contract

A *Pipeline's* name and version are a promise to the *User* about how it behaves, not a stamp on one particular implementation — the way one HTTP API serves `/v1` and `/v2` from one process. So everything that decides that behaviour is in the source, and nothing of it is configuration: which implementation, which *Models* it runs, the constants it slices with, and the name and version it is announced under. `registered_pipelines()` in [`pmcg_orchestrator/__init__.py`](pmcg_orchestrator/__init__.py) is the whole contract, one line per published *Pipeline*.

Changing any of it is a change to this program and a re-deployment. **Bump a pipeline's version whenever the same input would come out noticeably different** — a new *Model* snapshot, a change to the slicing, a change to the gluing. A bug fix that makes a *Pipeline* do what it always claimed to need not. The old and new versions of a *Pipeline* are both registered in the same process for as long as anyone may be pinning the old one, and they share whatever code they can.

An implementation class carries a version of its own — `PageFromStaffPipelineV2`, `GluePipelineV1` — which is the version of the behaviour it implements and is independent of the version it is published under, even where the two coincide, as they do for `mzk-page`.


## `mzk-page`

| | |
| --- | --- |
| Input | `image.jpg` |
| Output | `layout.json`, `Staves/{*}/image.jpg`, `Staves/{*}/transcription.musicxml`, `Staves/{*}/transcription.lmx` (optional), `transcription.musicxml` |

Four steps, and a *User* watching the page is told about each as it happens:

1. **Find the staves.** The layout *Model* — [dvorak-ola](../../models/dvorak-ola/README.md) — writes `layout.json`, a COCO document of page-structure boxes.
2. **Cut the page up.** One JPEG crop per `staff` box, written to `Staves/<n>/image.jpg` in reading order, with a margin of 0.9 of the staff's own height on every side — proportional so that it means the same thing on a 300dpi scan and a 600dpi one.
3. **Transcribe each staff.** The transcription *Model* runs once per staff, all of them dispatched at once, each producing `Staves/<n>/transcription.musicxml`.
4. **Glue them together** into one `score-partwise` document — and this is where the two versions differ.

Steps 1 and 3 are *Models*. Steps 2 and 4 are this *Pipeline's* own code, and are the parts that will move into a Musicorpus library when one exists — turning a page and its layout into subdivision crops is true of the format rather than of this deployment.

The intermediate *Files* stay in the page deliberately. They are what somebody looks at when the result is wrong, and a *MusicorpusPage* is discarded a few minutes later anyway.


### Version 2: a part per instrument

Version 2 reads the layout's `system` and `grandstaff` boxes as well as its staves. The `system` boxes say which staves sound at once, and the `grandstaff` boxes which two of them are one instrument; following each instrument from system to system down the page, every instrument becomes a `<part>`, holding its measures system after system with an explicit system break where each system begins.

- A grand staff's two staves are zipped into one two-staff part.
- Staves sharing a system are padded to the same number of measures, with a marked `Padding measure`.
- An instrument missing from a system is written there as hidden measure rests.
- The clef, key and time signature a staff does not print are carried over from that instrument's preceding staff.
- A page whose layout has no `system` boxes is read as one system, so its staves become that many instruments playing at once.

A failed staff keeps its place in its instrument's part, carrying the words `Cannot transcribe staff 7`.


### Version 1: the page as one instrument

Version 1 reads only the `staff` boxes. Every staff's measures go into one `<part>`, one staff after another, with a system break where each begins — which is what a page of solo music is, and it survives staves disagreeing about how many measures they have. What it cannot express is genuine polyphony: a piano system's two staves become two consecutive systems rather than one grand staff, and a four-part system becomes four systems. That is what version 2 is for.

(The first attempt gave each staff its own `<part>`, which is worse in the common case: it reads a solo piece as an N-instrument score whose parts sound at once, so nine staves of one melody become nine simultaneous melodies.)

A failed staff takes up a system of its own, carrying the words `Staff 7 could not be transcribed`.


### What both versions still do naively

**The slicing is a rectangle.** No deskewing, no straightening, no normalising of staff height. A transcription model that wants any of those should say so, and then it belongs in step 2 as a step of its own rather than smuggled into the crop.

**Reading order is down the page and then across.** A page laid out in two columns would have its staves interleaved. Finding the columns first is real work and is not done.

**One staff failing does not fail the page.** A scan of a real book has stains, cropped systems, and pages the detector was too generous about, so returning eleven staves of twelve is far more useful than returning an error. A failed staff is said in the log and in the document — in the document because an empty measure is otherwise indistinguishable from a staff the *Model* read as silence. A page where *every* staff failed does fail.


## `mzk-staff`

| | |
| --- | --- |
| Input | `Staves/{*s}/image.jpg` |
| Output | `Staves/{*s}/transcription.musicxml`, `Staves/{*s}/transcription.lmx` (optional) |

It runs the transcription *Model* on every staff crop it was given, and nothing else — the *User* has already done the cutting. Two things make it worth having beside the *Model's* own *ImplicitPipeline*:

**The name.** An *ImplicitPipeline* is called after the *Model* behind it, so it is `ayce-long 2026-08-03-192253-final` today and something else the day a better snapshot is deployed. `mzk-staff` `1` does not move when the snapshot does, so the *Web UI* can offer it and a *User* can pin it.

**Every staff of a page in one request.** Its *Signature* is the *Model's* own widened to a set, so a *User* transcribing a page's crops sends one request rather than one per staff. The *Model* still runs once per staff, all of them at once, so one staff failing fails that staff alone: it is said in the log, the rest are transcribed, and the request fails only when every staff did. One staff is still a valid set, which is what the *Web UI* sends, uploading a single crop to `Staves/1/image.jpg`.

`StavesFromStaffPipeline` has no version of its own: it does nothing but run the *Model*, so the version it is published under is the version of the choice of *Model*.


## `pmcg-slice` `1`

| | |
| --- | --- |
| Input | `image.jpg`, `layout.json` |
| Output | `Staves/{*}/image.jpg` |

Step 2 of `mzk-page` on its own, cutting exactly the crops `mzk-page` would have: it reads the `staff` boxes out of `layout.json` and writes `Staves/1/image.jpg` to `Staves/N/image.jpg`, numbered in reading order — top to bottom, and left to right between staves at the same height. It runs no *Model*.


## `pmcg-glue` `1` and `2`

| | |
| --- | --- |
| Input | `layout.json`, `Staves/{*}/image.jpg`, `Staves/{*}/transcription.musicxml` |
| Output | `transcription.musicxml` |

Step 4 of `mzk-page` on its own, in both of its versions: `pmcg-glue` `1` glues as `mzk-page` `1` does, `pmcg-glue` `2` as `mzk-page` `2` does. It runs no *Model*.

`layout.json` has boxes and no names, while the staves have names and no boxes, so they are paired by order:

- **Staff folder names must be integers**, and need not be contiguous. The *Musicorpus Specification* numbers every staff down the page, empty ones included, while the layout marks empty staves with a category of its own, so `Staves/1`, `Staves/2`, `Staves/4` is a perfectly good page. A folder that is not a number, or two folders that are the same number (`1` and `01`), are refused.
- **The staff images name the staves.** Only their names are used; nothing is read out of them. A staff with an image and no transcription is one that failed, and becomes a placeholder in the score exactly as it would in `mzk-page`. A transcription with no image is ignored, and said in the log. A page with no transcriptions at all fails.
- **The staves, sorted by number, are paired one to one with the `staff` boxes in reading order.** If the counts differ, as many are paired as can be, from the top — as python's `zip` pairs — and the rest on either side are left out and said in the log. Version 2 drops the unpaired boxes from the layout before working out the instruments, so they do not turn up as an instrument's silence.

`pmcg-slice` numbers its crops in exactly that reading order, so its output pairs up with no gaps. A placeholder in version 1 names the staff by its folder; in version 2, by its position in the layout.

The *Web UI* does not offer to run `pmcg-glue` on a page: its input names more than one pattern with a slot, and the *Web UI* deliberately does not guess how they go together ("needs several files matched to each other"). It is for the [Python client](../../../docs/using-python-client.md) and the HTTP API.


## Running the steps by hand

With the [Python client](../../../docs/using-python-client.md), holding one page open across the steps:

```py
from pathlib import Path

from musibot.client import MusibotClient

with MusibotClient(
    musibot_api_url="http://localhost:8000/musibot/api", api_token="secret"
) as client:
    page = client.create_page()
    client.upload_files(page.page_id, {"image.jpg": Path("scan.jpg").read_bytes()})

    def run(name: str, version: str, input: list[str]) -> None:
        execution = client.start_execution(page.page_id, name, version, input)
        client.wait_for_execution(page.page_id, execution.execution_id)

    def staves(suffix: str) -> list[str]:
        paths = [file.path for file in client.list_files(page.page_id)]
        return [path for path in paths if path.startswith("Staves/") and path.endswith(suffix)]

    run("dvorak-ola", "2.0-2025-03-09", ["image.jpg"])  # writes layout.json
    # ... a person may correct layout.json here, and upload it back ...
    run("pmcg-slice", "1", ["image.jpg", "layout.json"])
    run("mzk-staff", "1", staves("image.jpg"))
    run("pmcg-glue", "2", ["layout.json", *staves("image.jpg"), *staves("transcription.musicxml")])

    transcription = client.download_files(page.page_id, ["transcription.musicxml"])
    client.delete_page(page.page_id)
```

Left uncorrected, that `transcription.musicxml` is byte for byte the one `mzk-page` `2` writes for the same scan — tested here with fakes, and checked against the real *Models* on pages of the `UFAL.OmniOMR` corpus.


## Code layout

| Module | |
| --- | --- |
| `__init__.py` | `registered_pipelines()` — the published contract — the *Model* pins, the settings, and `main()`. |
| `page_from_staff.py` | `PageFromStaffPipeline` and its two versions, the steps of `mzk-page` strung together. |
| `staves_from_staff.py` | `StavesFromStaffPipeline`. |
| `slice.py`, `glue.py` | `SlicePipelineV1`, and `GluePipelineV1` and `V2` with the pairing they share. |
| `steps.py` | The steps the page, slice and glue *Pipelines* share — reading a layout, slicing a page — which is what keeps the pieces identical to the whole. |
| `layout.py` | Reading `layout.json`: its staves, and the instruments its systems and grand staves make of them. |
| `slicing.py` | Cutting a page image into staff crops, as plain functions over bytes. |
| `gluing/v1.py`, `gluing/v2.py` | The two gluings, as plain functions; `gluing/normalize.py` is version 2's clef, key and time carry-over. |


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

Running it needs the [local development stack](../../../deploy/README.md) and the `api` service:

```bash
.venv/bin/musibot-pmcg-orchestrator
```

`mzk-page` and `mzk-staff` also need a *Worker* for each *Model* they run — [dvorak-ola](../../models/dvorak-ola/README.md) and [zeus](../../models/zeus/README.md#running-it) with the `ayce-long` snapshot — which is the point at which a laptop is running the whole system. `pmcg-slice` and `pmcg-glue` run no *Model* and need none.


## Testing

`PipelineRunner` from the head's `testing` module stands in for the broker, object storage and the *Models*, so the tests are ordinary synchronous python and need none of Musibot running. The fake staff model writes real MusicXML and the fake layout model writes a real COCO document, so what is exercised is the parsing, the slicing arithmetic and the gluing rather than a mock agreeing with itself.

What every version of a *Pipeline* must do alike is tested once against each version (`test_page_from_staff.py`, and the shared half of `test_glue.py`), and what sets a version apart in a file of its own. Two tests hold the pieces to the whole: `pmcg-slice` must cut byte-identical crops to `mzk-page`, and `pmcg-glue` must write a byte-identical page from the *Files* `mzk-page` left behind, failed staves included.

```bash
.venv/bin/python -m pytest
.venv/bin/python -m ruff check .
.venv/bin/python -m ruff format --check .
.venv/bin/python -m mypy
```


## Versioning

Each *Pipeline's* name and version is what a *User* pins, and both are constants in the source — see [Pipeline versions are a contract](#pipeline-versions-are-a-contract). The package version in `pyproject.toml` is packaging only and nothing in Musibot reads it. See [Versioning and releases](../../../docs/versioning-and-releases.md).
