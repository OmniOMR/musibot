# Writing pipelines

*Pipelines* string together different *Models* to perform a useful recognition task for the *User*. This document explains how you write custom *Pipelines* and add them to the Musibot software system.

In this example we will build up a *Pipeline* that uses a staff detection model to find all the staves, then an end-to-end single-staff recognition model to transcribe each staff to MusicXML, and finally concatenates those into the page-level MusicXML file. But we will start with something much simpler.

[hello-orchestrator](../components/orchestrators/hello-orchestrator/) is the complete worked example that ships in this repository, and it runs. Read it when this page is not specific enough.


## A Pipeline is a class

Not a function, and the reason is worth having up front: the *Pipelines* that matter are **parametrized**. The same implementation is deployed twice — once pinning the *Model* snapshot that production uses, once pinning the one being developed — and it must not be copied to do that. Constructor arguments are where those parameters go.

```py
from musibot.orchestrator_head import Pipeline, PipelineContext, Signature


class HelloWorldPipeline(Pipeline):
    """A Musibot pipeline that produces a Hello World MusicXML file."""

    name = "hello-world"
    version = "1.0.0"
    signature = Signature(input=["image.jpg"], output=["transcription.musicxml"])

    async def execute(self, ctx: PipelineContext) -> None:
        ctx.logger.info("Reading image.jpg ...")
        image = await ctx.read_bytes("image.jpg")

        ctx.logger.info("Building transcription.musicxml ...")
        await ctx.write_text("transcription.musicxml", musicxml(f"Hello World! ({len(image)} bytes)"))

        ctx.logger.info("Done.")
```

Three attributes and one method:

- **`name` and `version`** are how a *User* asks for this *Pipeline*. The version is an opaque string that Musibot never parses, so `4`, `1.2.0` and `2026-07-22` are equally good.
- **`signature`** declares which sets of *Files* this reads and writes. It is *patterns*, not paths — `Staves/{s}/image.jpg` rather than `Staves/7/image.jpg` — and it is what makes your *Pipeline* usable by someone who has never read its code. See [Signatures](signatures.md).
- **`execute`** does the work for one *MusicorpusPage*, within a few seconds to minutes.

Set the three as class attributes when they are fixed, or in `__init__` when they follow from the parameters. A *Pipeline* that leaves one out is refused when it is registered, rather than appearing in the listing as something nobody can call.


## What the context can do

`ctx` is the whole of the API between a *Pipeline* and the rest of Musibot:

| | |
| --- | --- |
| `ctx.input` | the *Files* the *User* asked to have processed |
| `ctx.parameters` | what the *User* sent with this one execution |
| `ctx.page_id`, `ctx.execution_id` | which execution this is |
| `ctx.logger.info(...)` | a line for whoever is watching this page |
| `await ctx.read_bytes(path)`, `read_text` | one *File* out of the page |
| `await ctx.write_bytes(path, data)`, `write_text` | one *File* into the page |
| `await ctx.list_files()`, `exists(path)` | what the page holds |
| `await ctx.execute_model(model, input=[...])` | run one *Model* and wait for it |

The file methods are named after `pathlib`'s and behave as you would expect, except that each one reaches object storage — which is why they are coroutines. `ctx.logger` is not: a log line is fire-and-forget, so awaiting your own narration would buy nothing.

Two things about `ctx.input` are worth being precise about. It is the *User's* choice of *Files*, already checked by the `api` service against the *Signature* you declared, so it fits the shape you announced — but which *Files* it names, only it knows. And unlike a *Model's* input list it does **not** bound what you may read: nothing is staged for a *Pipeline*, and a real one writes and re-reads intermediate *Files* that did not exist when it started.

The pipeline above reads `image.jpg` outright because that is the only thing it is for. A *Pipeline* that works at the staff level takes the staves from `ctx.input` instead.


## Running it

A *Pipeline* in isolation is of no use — it has to be registered into an *Orchestrator* and run by one. Create a new python project, add [orchestrator-head](../components/orchestrator-head/) as a dependency, and write its startup script:

```py
from musibot.orchestrator_head import Orchestrator, OrchestratorHeadSettings

from my_orchestrator.hello_world import HelloWorldPipeline


def main() -> None:
    settings = OrchestratorHeadSettings.load()

    orchestrator = Orchestrator("my-orchestrator", settings)
    orchestrator.register_pipeline(HelloWorldPipeline())
    orchestrator.run()
```

That is an *Orchestrator*: a name, a set of *Pipelines*, and the process that serves them. Start it against an existing RabbitMQ and MinIO and `hello-world` is visible in Musibot:

```bash
python3 -m my_orchestrator \
    --rabbit-host localhost \
    --rabbit-user root \
    --rabbit-password password \
    --s3-endpoint-url http://localhost:9000 \
    --s3-access-key root \
    --s3-secret-key password
```

Now you can test the pipeline, for example from the Web UI.

> **Note:** The process is configured like any other Musibot service — command line arguments, environment variables, or a config file. The values above are in fact the defaults, so against the [local development stack](../deploy/README.md) you can start the orchestrator with no arguments at all. See [Service configuration](service-configuration.md).

Nothing had to be configured on the `api` service's side. An *Orchestrator* is plugged into a running system just by connecting to RabbitMQ, and [Discovery](discovery.md) does the rest — which also means you can plug an *Orchestrator* running on your laptop into a shared system and watch it take work.


## Parameters, of which there are two kinds

The word means two different things, and they arrive by different routes:

| | Comes from | Reaches the *Pipeline* as | Changes |
| --- | --- | --- | --- |
| **Registration parameters** | the *Orchestrator's* own configuration | constructor arguments | never, for the life of the process |
| **Execution parameters** | the *User*, on one request | `ctx.parameters` | every execution |

Registration parameters are the interesting ones, and they are what a class buys you. Give your *Pipeline* a constructor:

```py
from musibot.orchestrator_head import NameAndVersion, Pipeline, PipelineContext, Signature


class MzkPipeline(Pipeline):
    signature = Signature(input=["image.jpg"], output=["transcription.musicxml"])

    def __init__(
        self,
        name: str,
        version: str,
        *,
        layout_model: NameAndVersion,
        staff_model: NameAndVersion,
    ):
        self.name = name
        self.version = version
        self._layout_model = layout_model
        self._staff_model = staff_model
```

…and an *Orchestrator* that gets those parameters from its own settings:

```py
class OmniOmrSettings(OrchestratorHeadSettings):
    staff_model_version: str = "2026-07-22"
    staff_model_dev_version: str = "2026-08-01"


def main() -> None:
    settings = OmniOmrSettings.load()
    layout_model = NameAndVersion(name="dvorak-ola", version="2.0-2025-03-09")

    orchestrator = Orchestrator("omniomr", settings)

    orchestrator.register_pipeline(
        MzkPipeline(
            "mzk",
            "4",
            layout_model=layout_model,
            staff_model=NameAndVersion(name="zeus", version=settings.staff_model_version),
        )
    )
    orchestrator.register_pipeline(
        MzkPipeline(
            "mzk-dev",
            "5",
            layout_model=layout_model,
            staff_model=NameAndVersion(name="zeus", version=settings.staff_model_dev_version),
        )
    )

    orchestrator.run()
```

Two *Pipelines*, one implementation, no code copied — and `--staff-model-dev-version` is a command line argument, an environment variable and a config-file key, because `OrchestratorHeadSettings` is an ordinary Musibot settings class. Subclass it and every field you add gets all three, plus a line in `--help`.

Note the order: **settings are loaded first, and the *Pipelines* are built from them.** That is what lets a command line argument reach a constructor, and it is why `run()` takes no arguments.


## Invoking a Model

Within `execute`, a *Model* is run like this:

```py
await ctx.execute_model(self._layout_model, input=["image.jpg"])
```

The *Model* is pinned by name **and version, exactly**. There is no loose version selection and none is planned: exact pinning is what makes a *Pipeline* reproducible, and a *Pipeline* that wants to follow a moving *Model* takes the version as a registration parameter — which is precisely what `mzk-dev` above does.

There is nothing to return. Whatever the *Model* produces lands in the page's storage, so a *Pipeline* learns what it did by reading the *Files* it left behind:

```py
    async def execute(self, ctx: PipelineContext) -> None:
        ctx.logger.info("Detecting staves ...")
        await ctx.execute_model(self._layout_model, input=["image.jpg"])

        layout = json.loads(await ctx.read_text("layout.json"))
        staves = [a["bbox"] for a in layout["annotations"] if a["category_id"] == STAFF]
        ctx.logger.info("Found %d staves.", len(staves))
```

A *Model* that fails raises `ModelExecutionFailed`, carrying the reason the *Model* gave. Let it propagate unless you have something better to do about it — see [Failing](#failing) below.


## Slicing the page

Now the *Pipeline* does some work of its own: cut the image into one crop per staff and write each one where the staff transcription *Model* expects to find it.

```py
        ctx.logger.info("Slicing the page into staves ...")
        page = Image.open(BytesIO(await ctx.read_bytes("image.jpg")))

        for number, (x, y, width, height) in enumerate(staves, start=1):
            crop = BytesIO()
            page.crop((x, y, x + width, y + height)).save(crop, format="JPEG")
            await ctx.write_bytes(f"Staves/{number}/image.jpg", crop.getvalue())
```

This is ordinary python with an ordinary dependency — Pillow here, OpenCV just as well. Your *Orchestrator* brings whatever its *Pipelines* need; that is why it has a virtual environment of its own.

> **Not yet implemented:** slicing a page into staves and concatenating staff MusicXML into a page-level file are things every real *Pipeline* wants, and Musibot provides neither. They belong in a Musicorpus library rather than in the *Orchestrator Head*, which knows only that a *File* is bytes.


## Running a Model over every staff

The staves are independent, so transcribe them concurrently. This is plain `asyncio`:

```py
        ctx.logger.info("Transcribing %d staves ...", len(staves))
        async with asyncio.TaskGroup() as group:
            for number in range(1, len(staves) + 1):
                group.create_task(  # no await, on purpose
                    ctx.execute_model(
                        self._staff_model, input=[f"Staves/{number}/image.jpg"]
                    )
                )
```

Each of those becomes its own `model-execution-start` on the broker, so a page with twelve staves keeps twelve *Workers* busy if that many are running — which is exactly how a *Model* scales horizontally. A `TaskGroup` waits for all of them and, if one fails, cancels the rest and raises.

When you did not name the *Files* yourself, ask the page what it holds:

```py
        staff_images = sorted(path for path in await ctx.list_files() if path.endswith("/image.jpg"))
```

That is the case whenever a *Model* invented the names — a splitter declaring `Staves/{*}/image.jpg` decides how many staves there are, and nothing else could have known.


## Finishing the page

Read each staff's transcription back and concatenate them into the page-level file, one `<part>` per staff:

```py
        ctx.logger.info("Concatenating the staves ...")
        transcriptions = [
            await ctx.read_text(f"Staves/{number}/transcription.musicxml")
            for number in range(1, len(staves) + 1)
        ]

        await ctx.write_text("transcription.musicxml", concatenate(transcriptions))
        ctx.logger.info("Done.")
```

Every `write_*` reaches object storage and is announced as it lands, so a *User* watching the page sees each *File* appear rather than everything at the end.


## Testing a Pipeline

A *Pipeline* is ordinary python, and it should be testable the way ordinary python is. `PipelineRunner` stands in for the whole *Orchestrator Head* — it is the storage your *Pipeline* reads and writes, the log it talks to, and the *Models* it invokes:

```py
from musibot.orchestrator_head.testing import PipelineRunner


def test_it_transcribes_every_staff() -> None:
    runner = PipelineRunner({"image.jpg": JPEG})
    runner.register_model(LAYOUT_MODEL, lambda call, files: files.update({"layout.json": LAYOUT}))
    runner.register_model(STAFF_MODEL, transcribes_a_staff)

    runner.run(MzkPipeline("mzk", "4", layout_model=LAYOUT_MODEL, staff_model=STAFF_MODEL),
               input=["image.jpg"])

    assert "transcription.musicxml" in runner.files
    assert len(runner.model_calls) == 3
    assert "Found 2 staves." in runner.log_messages()
```

No broker, no object storage, no *Models* — and no async test framework either, because `run` is synchronous. (`run_async` is there for a test that is already on an event loop.)

A fake *Model* is whatever you say it is: the behaviour you register is handed the call and the page's *Files*, and may write into them exactly as a real *Model* would. Raise from it to exercise the failure path. A *Pipeline* that runs a *Model* you did not register fails the test loudly rather than looking like a pass.

Afterwards `runner.files`, `runner.logs`, `runner.model_calls` and `runner.written` are what your *Pipeline* did. The runner also applies the same input-list check the `api` service does, so a test cannot hand your *Pipeline* a list a *User* could never send.


## Failing

Raise. The exception's message becomes the error of the *Pipeline Execution* and reaches the *User* who was waiting, so it is worth writing for a human — `"No staves found on this page."` beats a fragment of a traceback.

```py
        if not staves:
            raise ValueError("No staves found on this page.")
```

You do not have to catch anything for the *Orchestrator* to stay up: an execution that raises is reported failed and the process goes on serving the next one. A `ModelExecutionFailed` you do not catch does the same thing, carrying the *Model's* own reason with it.

Two things happen on a clock, and neither is yours to implement. Every execution carries a deadline, and a *Pipeline* that outruns it is cancelled and reported failed. And a *User* who gives up cancels the execution, which cancels your `execute` where it stands — so if you hold a resource across an `await`, release it in a `finally` as you would anywhere else.


## Wrapping up

We built a *Pipeline* that strings two *Models* together to perform full-page music recognition, deployed it in an *Orchestrator*, gave it registration parameters so that one implementation serves both production and development, and tested it without any of Musibot running.

What to read next:

- [orchestrator-head](../components/orchestrator-head/README.md) — the reference for everything used here.
- [hello-orchestrator](../components/orchestrators/hello-orchestrator/README.md) — a small, complete, running example.
- [Signatures](signatures.md) — what a *Signature* can say, and what Musibot checks.
- [Deploying onto a VM](deploying-to-a-vm.md#8-an-orchestrator) — running an *Orchestrator* under systemd.
