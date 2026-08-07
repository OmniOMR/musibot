# dvorak-ola

A *Model* that reads the **layout** of a page of sheet music: where the staves are, which of them group into systems and grandstaves, and where the measures fall. It transcribes nothing — locating things is the whole job. It is the first half of a page-level recognition pipeline whose second half cuts the page up along these boxes and hands the crops to a transcription model such as [zeus](../zeus/), which today can only be given a staff someone cropped by hand.

The recognition itself is [Vojtěch Dvořák's OMR Layout Analysis](https://github.com/v-dvorak/omr-layout-analysis) — a `yolo11m` detector trained on AudioLabs v2, MUSCIMA++, OSLiC and the author's own MZKBlank, some 7 000 pages and half a million boxes. Around a thousand of those pages are covers, title pages and tables of contents carrying no music at all, which is worth knowing: a page with nothing on it is a case the checkpoint was trained for rather than one it has never seen. What lives here is the wrapper: the [worker IPC contract](../../../docs/worker-ipc.md), and the translation of what the checkpoint predicts into a Musicorpus `layout.json`.


## What it does

| | |
| --- | --- |
| Name and version | `dvorak-ola` `2.0-2025-03-09` |
| Input | `image.jpg` — a whole page |
| Output | `layout.json` |
| Batching | No — see [Not yet exercised](#not-yet-exercised) |
| Python | 3.10 or newer, and its own virtual environment |

One page in, one COCO file out. The *Signature* has no slots in it, which makes it the simplest kind there is: a page-level *Model* whose *ImplicitPipeline* is exactly "upload a scan, get a layout".


## The classes, and their Musicorpus names

The checkpoint predicts five classes under the names it was trained with, and the [Musicorpus Specification](https://github.com/OmniOMR/musicorpus/blob/main/spec/musicorpus-specification.md) names the same things differently. `layout.json` is defined in the specification's vocabulary, so the translation happens here:

| The checkpoint says | `layout.json` says | Which is |
| --- | --- | --- |
| `staves` | `staff` | One staff carrying music. |
| `stave_measures` | `staffMeasure` | One measure within a staff. |
| `systems` | `system` | Staves that sound together. |
| `system_measures` | `systemMeasure` | One measure across a system. |
| `grand_staff` | `grandstaff` | A pianoform pair of staves. |

The table is read out of the checkpoint at startup rather than assumed: `names` is written into a YOLO file at training time, so a class this model has no Musicorpus name for is logged and its detections dropped, instead of being silently renumbered by a later release.

**Two specification classes are never produced.** `emptyStaff` is not one the model was trained to find — its training data marks a staff only when it carries music, which is the same distinction the specification draws, so what it finds is `staff` and the empty ones are simply absent rather than misfiled. And `grandstaffMeasure` is not predicted either; the specification itself notes it can be recovered by intersecting `grandstaff` with `systemMeasure`, and asks that a producer say which classes it does not support. This paragraph is that.


## The `layout.json` it writes

A COCO object-detection document, as the specification defines the file: `bbox` in `[x, y, width, height]` pixels of the page image, `area` the box's area, `segmentation` exactly the rectangle the box describes, `iscrowd` always `0`. Category IDs are fixed rather than assigned per page — the specification's own example numbering — so that a `staff` is category `0` in every file this model writes. Only the categories a page actually has are listed, which is what the specification asks for.

Boxes are rounded **outwards** to whole pixels and clamped to the image: the specification asks for a box that fully contains its object, and half a pixel of slack costs less than a clipped staff line. Annotations come out ordered by category and then down the page, so that running the same model over the same page twice produces the same bytes.

Three details depart from a literal reading of the specification, and all three come from the same fact — **the specification describes a dataset, and this file is written into a working *Musicorpus Page*** that belongs to a *User* and is discarded when they are done with it:

- **`info` describes the producer, not a dataset.** Its fields are defined as copies of `musicorpus.json`, which does not exist here. They are filled with what is true instead: `description` is the model and version that wrote the file, `url` the repository the weights came from, `date_created` the day it was written. That makes the block provenance, which is the useful thing to know about a file a machine produced.
- **`licenses` is absent, and so is `images[0].license`.** The image is a scan a *User* uploaded a few seconds ago. Musibot knows nothing about the rights in it, and a license entry is a claim; leaving the field out says "not stated", which is the truth.
- **`images[0].date_captured` is absent** for the same reason. The specification allows falling back to the dataset's creation date; there is no dataset, and the moment the model looked at the scan is not when it was captured.

One field is *added*: each annotation carries a **`score`**, the detector's confidence between 0 and 1. The specification says nothing about confidence because it describes hand-checked ground truth, and this is a prediction. It is kept because thresholding downstream can only ever go upwards — whatever `--confidence` dropped is gone — so discarding the score would force a second forward pass to get it back. Consumers that do not want it can ignore it; the [Web UI](../../web-ui/) already does.


## Parameters

A *Pipeline* hands a *Model* its knobs through the `parameters` object on each execution, and every one of these is also a command-line default for the deployment:

| Parameter | Default | What it does |
| --- | --- | --- |
| `confidence` | `0.25` | Detections the model is less sure of than this are dropped. |
| `iou` | `0.7` | How much two boxes of one class may overlap before the weaker is dropped. |
| `image_size` | `640` | What the page is scaled to before it is looked at. |
| `max_detections` | `1000` | A ceiling on how many objects one page may have. |

Two of them are worth a sentence more.

**`image_size`** is the one that decides what the model can see. The checkpoint was trained at 640, so that is the honest default and it is where the model behaves as its author measured it — but a page scan is several thousand pixels across, and what a downscale takes away is the small things first. A `system` survives it easily; a `staffMeasure` on a dense page may not. A *Pipeline* that wants measures rather than throughput has a reason to raise this, and one that only wants staves has none.

**`max_detections`** is set well above ultralytics' own default of 300, because a page of dense orchestral music passes 300 on measures alone — the training data averages around seventy objects per page and the busy pages are several times that. Hitting the ceiling is silent, so it is set where reaching it means something has gone wrong rather than where it merely bites.

Anything unusable is refused as a failure of *that* execution, naming the parameter, rather than becoming a stack trace out of the middle of ultralytics.


## Weights

Not in this repository, and not fetched at run time. [The release](https://github.com/v-dvorak/omr-layout-analysis/releases/tag/ola-v2.0) is a single 40 MB `.pt`:

```bash
mkdir -p weights
curl -Lo weights/ola-layout-analysis-2.0-2025-03-09.pt \
    https://github.com/v-dvorak/omr-layout-analysis/releases/download/ola-v2.0/ola-layout-analysis-2.0-2025-03-09.pt
```

Downloading it by hand is deliberate. A deployed *Model* is given nothing writable but its pages directory, so one that fetched its weights on demand would fail on its first execution rather than on the day the download is slow — and `--weights` is checked before anything else, so a missing file is a message at startup and not a puzzle inside ultralytics.

**A YOLO checkpoint carries no identity of its own.** Zeus reads its name and version out of its snapshot precisely so the two cannot drift; there is nothing to read here, so `--model-version` states it and has to be kept in step by hand. Serving a different checkpoint without changing it merges two different models into one registry entry, and a *Pipeline* that pinned the version then gets whichever *Worker* answered. The default is the release this package was written against.


## Development

```bash
cd components/models/dvorak-ola
python3 -m venv .venv
.venv/bin/pip install -e '.[dev]'
```

That pulls torch, so it is a slow install and a couple of gigabytes; nothing else in Musibot has a dependency of that size, which is the whole reason a *Model* gets a virtual environment of its own.


## Running it

A *Model* is never started by hand — a *Worker Head* launches it and hands it the two file descriptors it talks over. Against the [local development stack](../../../deploy/README.md), reaching MinIO directly, every other setting already defaults correctly:

```bash
cd components/worker-head
.venv/bin/musibot-worker-head --model-command \
    "$PWD/../models/dvorak-ola/.venv/bin/musibot-dvorak-ola --weights $PWD/../models/dvorak-ola/weights/ola-layout-analysis-2.0-2025-03-09.pt"
```

Add `--s3-bucket musibot --s3-key-prefix s3/` when the `api` service is the one behind the proxied topology, since a *Worker* that is rooted differently from the `api` service does not fail — it simply stops seeing its objects and reports that its input file does not exist.

It then appears in `GET /pipelines` as an *ImplicitPipeline* — upload an `image.jpg`, get a `layout.json` — which the Web UI will draw over the scan.


## Deploying it

The steps that surround this — the VM, RabbitMQ, MinIO, the `musibot-worker@.service` template — are in [Deploying onto a VM](../../../docs/deploying-to-a-vm.md). This is the dvorak-ola-specific part of section *A worker*.

Two virtual environments, as for [zeus](../zeus/README.md#deploying-it), though for a milder reason: this model would run on the same python as the *Worker Head*, but torch and its several gigabytes have no business in the head's environment, and pinning them together means one of the two cannot be upgraded alone. **The model is installed once**, at `/opt/musibot/models/dvorak-ola/`, and every worker running it shares that directory. **The head is per instance**, at `/opt/musibot/workers/<instance>/`.

```bash
# the model, with its own torch
sudo -u musibot python3.12 -m venv /opt/musibot/models/dvorak-ola/venv
sudo -u musibot /opt/musibot/models/dvorak-ola/venv/bin/pip install \
    'musibot-dvorak-ola @ git+https://github.com/OmniOMR/musibot.git@main#subdirectory=components/models/dvorak-ola'

# the checkpoint, downloaded now rather than by the model when it starts
sudo -u musibot mkdir -p /opt/musibot/models/dvorak-ola/weights
sudo -u musibot curl -Lo \
    /opt/musibot/models/dvorak-ola/weights/ola-layout-analysis-2.0-2025-03-09.pt \
    https://github.com/v-dvorak/omr-layout-analysis/releases/download/ola-v2.0/ola-layout-analysis-2.0-2025-03-09.pt

# the worker head, on the 3.12 the rest of Musibot is developed on
sudo -u musibot python3.12 -m venv /opt/musibot/workers/ola-2.0-2025-03-09/venv
sudo -u musibot /opt/musibot/workers/ola-2.0-2025-03-09/venv/bin/pip install \
    'musibot-core @ git+https://github.com/OmniOMR/musibot.git@core/v0.1.0#subdirectory=components/core' \
    'musibot-worker-head @ git+https://github.com/OmniOMR/musibot.git@worker-head/v0.1.0#subdirectory=components/worker-head'
```

A CPU-only VM wants the CPU wheel of torch rather than the default one, which drags in several gigabytes of CUDA that will never run: `pip install --index-url https://download.pytorch.org/whl/cpu torch` before the line above.

The instance is named after the checkpoint, for the reasons in [Naming a worker instance](../../../docs/deploying-to-a-vm.md#naming-a-worker-instance):

```bash
instance=ola-2.0-2025-03-09

sudo install -o root -g musibot -m 0640 \
    components/models/dvorak-ola/worker-dvorak-ola.env.example "/etc/musibot/worker-$instance.env"
sudo nano "/etc/musibot/worker-$instance.env"        # fill in the credentials

sudo systemctl enable --now "musibot-worker@$instance"
journalctl -u "musibot-worker@$instance" -f
```

A healthy start logs the configuration, then this model's own `dvorak-ola 2.0-2025-03-09 loading …` and `… ready` (a model's stdout is captured as its log), and then the head announcing itself to the registry. `GET /musibot/api/pipelines` should list the implicit pipeline within a heartbeat.

Read the comments at the end of that environment file before running two of these on one VM. Ultralytics needs somewhere writable to put its settings, wants telling not to phone home, and torch will size its thread pools to the whole machine unless told otherwise.


## Licensing

**This is the one component of Musibot that is not Apache-2.0.** It is [AGPL-3.0-or-later](LICENSE), because it exists to `import ultralytics` and ultralytics is AGPL-3.0. The rest of the monorepo does not move: Apache-2.0 is one-way compatible *into* AGPL-3.0, so a copyleft folder inside a permissive repository is a normal arrangement rather than a contradiction. What follows is the reasoning, because the conclusion is worth being able to check rather than take on trust.

None of this is legal advice, and none of it has been through anyone qualified to give it. It is written down so that whoever does decide is starting from the facts.


### Why a running service is the case that matters

Ordinary GPL is triggered by *distribution*, and a web service distributes nothing — which is the loophole AGPL exists to close. Its §13 adds that users interacting with the program **over a network** must be offered its Corresponding Source, as though they had been shipped a copy. A publicly reachable Musibot instance is precisely the case the clause was drafted for, so there is no argument to be had about whether it applies in principle. Running this *Model* on a laptop, or inside an institution that publishes nothing, triggers nothing at all.


### How far it reaches

The question is what counts as one work together with ultralytics, and the conventional answer is the address space: code linked into one process is a combined work, while separate programs exchanging data at arm's length over pipes or sockets are not.

Musibot's [worker IPC boundary](../../../docs/worker-ipc.md) falls on the useful side of that line, and it is worth being clear that this is luck rather than design — the boundary exists because a *Model* must be able to bring its own python, and it happens to be the same boundary copyleft cares about:

| | Imports ultralytics | Standing |
| --- | --- | --- |
| `musibot-dvorak-ola` — this package | Yes, in [`detector.py`](dvorak_ola/detector.py) | Inside the combined work. Hence the licence. |
| `worker-head`, `core`, `api`, `web-ui`, `python-client`, *Orchestrators*, [zeus](../zeus/) | No — they reach this *Model* only over the pipes and RabbitMQ | Separate works, and Apache-2.0 as before. |

So the exposure is one folder rather than the monorepo. **That reading is defensible rather than settled**: whether a python `import` creates a derivative work has not been litigated, and Ultralytics sells an Enterprise Licence premised on the broader reading, which makes their interpretation a commercial position and not merely an opinion. Anyone publishing this should know they are relying on the narrow one.


### What a public deployment therefore owes

Little, because Musibot is already public — but §13 asks for a **prominent offer** to network users, which source that merely exists somewhere does not satisfy:

- A visible link to the source from the *Web UI*, or a documented endpoint that serves one.
- Pointing at the version actually running. A link to `main` is not the Corresponding Source of what answered the request; publish the tag or the commit.
- Covering this package and the scripts that install it.

And it reaches no further than that. A *User's* scans and the `layout.json` written for them are **output of running the program**, not part of it, and nothing here asks for them. Neither does anything ask for the components in the second row above, on the reading described.


## Not yet exercised

**Batching.** Pages are independent, so this *Model* could advertise `supports_batching` and put several through one forward pass — which is most of what makes GPU inference fast. It says `False` today, because the *Worker Head* [never sends `execute-batch`](../../worker-head/README.md#not-yet-implemented), and because doing it properly is more than passing a list to ultralytics: one unreadable image must fail one execution rather than the batch, which means loading the images before the forward pass instead of handing over paths. Worth doing when the head can drive it and there is a GPU under it; not worth carrying as untested code until then.

**Tiling.** The model is run over the whole page at once, as its author's own prediction script does. `image_size` is the only lever on what a downscale costs, and the alternative — cutting the page into overlapping tiles, detecting in each, and merging the boxes back — is what would actually recover small measures on a large scan. That is a change to this model's inference, not to Musibot, and belongs here if the measure classes turn out to matter.


## Testing

The ultralytics call is the only part that needs torch; everything else — the IPC exchange, the COCO document, the parameter handling — is driven against a fake detector over in-memory streams, with no subprocess, no pipes and no *Worker Head*.

```bash
.venv/bin/python -m pytest
.venv/bin/python -m ruff check .
.venv/bin/python -m ruff format --check .
.venv/bin/python -m mypy
```
