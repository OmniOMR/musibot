# Writing pipelines

*Pipelines* string together different *Models* to perform a useful recognition task for the *User*. This document explains how you can write custom *Pipelines* and add them to the Musibot software system.

In this example we will write a *Pipeline* that uses a staff detection model to find all the staves, then an end-to-end single-staff recognition model to transcribe each staff to MusicXML and finally the pipeline will concatenate these staff transcription to get the page-level MusicXML file. But before we get there, we will start with simple steps first.


## Hello World pipeline first

A *Pipeline* is a python `async` function that does all the necessary processing for a single *MusicorpusPage* within a few seconds to minutes. Let's take a simple pipeline that always produces the same MusicXML file with Hello World contents:

```py
from musibot.orchestrator_head import PipelineContext
import xml.etree.ElementTree as ET
import cv2


async def hello_world_pipeline(ctx: PipelineContext):
    """Musibot pipeline that produces a Hello World MusicXML file"""
    
    # get the size of the input image
    ctx.logger.info("Reading image.jpg ...")
    image_bytes: bytes = await ctx.read_file_bytes("image.jpg")
    image = cv2.imdecode(image_bytes, cv2.IMREAD_COLOR)
    (height, width, _) = image.shape
    
    # produce a Hello World MusicXML file with the image size
    ctx.logger.info("Building transcription.musicxml ...")
    musicxml = f"""
    <?xml version="1.0" encoding="UTF-8"?>
    <score-partwise version="4.0">
    <part-list>
        <score-part id="P1">
            <part-name>Piano</part-name>
        </score-part>
    </part-list>
    <part id="P1">
        <measure>
            <attributes>
                <divisions>1</divisions>
                <clef>
                    <sign>G</sign>
                    <line>2</line>
                </clef>
            </attributes>
            <note>
                <rest measure="yes"/>
                <duration>4</duration>
                <voice>1</voice>
                <type>whole</type>
                <lyric>
                    <text>
                        Hello World! ({width}x{height})
                    </text>
                </lyric>
            </note>
        </measure>
    </part>
    </score-partwise>
    """
    ctx.write_file_string("transcription.musicxml", musicxml)

    ctx.logger.info("Done.")
```

The pipeline function gets a `ctx` context object that acts as the API for communication with the rest of the Musibot system. From what we can see:

- `ctx.logger.info(...)` Prints messages to the pipeline execution log.
- `ctx.read_file_bytes(...)` Reads a binary *File* from the current *MusicorpusPage* directory.
- `ctx.write_file_string(...)` Writes a text *File* to the current *MusicorpusPage* directory.


## Orchestrator deployment

A *Pipeline* in isolation is of no use. It must be registered into the Musibot system and executed by something. This connector is the *Orchestrator Head* framework. We could add the *Pipeline* into an existing *Orchestrator* codebase, however, we will create a new *Orchestrator* here instead, to see how you can get started with *Orchestrators*.

Create a new python project and add *Orchestrator Head* as a dependency. Then create the `orchestrator.py` startup script in it and paste there this content:

```py
from musibot.orchestrator_head import Orchestrator, Pipeline
from hello_world_pipeline import hello_world_pipeline


orchestrator = Orchestrator()

orchestrator.register_pipeline(
    Pipeline(
        name="hello-world",
        version="1.0.0", # TODO: pipeline versioning is not yet clear (string / int / semver?)
        implementation=hello_world_pipeline
    )
)

orchestrator.run()
```

Now you can start the orchestrator process and connect it to an existing RabbitMQ and MinIO to make the `hello-world` pipeline visible in Musibot:

```bash
python3 orchestrator.py \
    --rabbit-host localhost \
    --rabbit-user root \
    --rabbit-password password \
    --s3-endpoint-url http://localhost:9000 \
    --s3-access-key root \
    --s3-secret-key password
```

Now you can test the pipeline, for example, from the Web UI.

> **Note:** The process may be configured just like any other of the core services via command line arguments, environment variables, or a config file. The values above are in fact the defaults — against the [local development stack](../deploy/README.md) you can start the orchestrator with no arguments at all. See [Service configuration](service-configuration.md) for more.


## Invoking the staff detection model

Now that we have a barebones *Pipeline* ready and running, we will extend it to provide our desired functionality.

Within any *Pipeline*, you can invoke a *Model* like this:

```py
async def my_pipeline(ctx: PipelineContext):
    ...
    
    await ctx.execute_model(
        name="my-model",
        version="2026-07-22", # TODO: what about loose model version selection?
        input={"image.jpg"}, # TODO: what about additional model arguments? JSON payload specific to that model? likely.
    )

    ...
```

For our pipeline, we assume we have the `staff-detector` model already running. If not, go through the [Adding models](adding-models.md) guide first. We can just call the model at the beginning of our pipeline to generate the `layout.json` file.

```py
from musibot.orchestrator_head import PipelineContext
from musibot.musicorpus import slice_image_to_staves


async def hello_world_pipeline(ctx: PipelineContext):
    """Musibot pipeline that produces a Hello World MusicXML file"""

    # create the layout.json file with staff bboxes
    ctx.logger.info("Running the staff detector ...")
    await ctx.execute_model(
        name="staff-detector",
        version="2026-07-22",
        input={"image.jpg"},
    )

    # use Musicorpus logic inside Musibot to create
    # staff-level crops of the image
    ctx.logger.info("Slicing image to staves ...")
    slice_image_to_staves(ctx)  # TODO: this is a placeholder for something more elaborate
    
    # Now we should have `Staves/*/image.jpg` files ready
```


## Invoking the staff transcription model

Now we need to run the `staff-transcriptor` model (see [Adding models](adding-models.md) guide) on each staff image in parallel and wait when all are done:

```py
from musibot.orchestrator_head import PipelineContext
from musibot.musicorpus import slice_image_to_staves
import asyncio


async def hello_world_pipeline(ctx: PipelineContext):
    ...

    # execute staff transcription model once for each staff in parallel
    ctx.logger.info("Starting staff transcription ...")
    async with asyncio.TaskGroup() as tg:
        for staff_number in ctx.page.staves:
            tg.create_task(
                ctx.execute_model(  # No await on purpose!
                    name="staff-transcriptor",
                    version="2026-07-22",
                    input={f"Staves/{staff_number}/image.jpg"},
                )
            )

    # Now we should have `Staves/*/transcription.musicxml` files ready
```


## Concatenating MusicXML

The last remaining step is concatenating the staff-level MusicXML files into a single page-level MusicXML file by treating each staff as a separate `<part>`.


```py
from musibot.orchestrator_head import PipelineContext
from musibot.musicorpus import concatenate_staff_musixml_to_page


async def hello_world_pipeline(ctx: PipelineContext):
    ...

    # use Musicorpus logic inside Musibot to create page-level MusicXML file
    ctx.logger.info("Concatenating MusicXML staves ...")
    concatenate_staff_musixml_to_page(ctx)  # TODO: this is a placeholder for something more elaborate
    
    # Now we should have `transcription.musicxml` file ready,
    # which is our final output
```


## Wrapping up

In this guide we've built a simple Musibot *Pipeline* that strings together two different *Models* to perform full-page music recognition. We also learned how to deploy this pipeline in a custom *Orchestrator*.
