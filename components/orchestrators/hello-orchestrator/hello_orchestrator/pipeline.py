"""A *Pipeline* that recognises nothing and proves the plumbing works.

It does the three things a real *Pipeline* does, and nothing else:

1. **Invokes a *Model*** — `hello-model`, whose name and version are
   registration parameters rather than literals, because that is how a real
   *Pipeline* is pinned to a *Model* snapshot.
2. **Reads what that *Model* produced** and says so in the log, which is the
   part a *User* watching the page actually sees.
3. **Reads and writes *Files* of the page**, producing a `layout.json` with one
   staff inset from the edges of the image.

The staff it "finds" is made up. That is the point: everything around it —
discovery, the work queue, the model round trip, the log stream, object storage
— is real, and this is the smallest *Pipeline* that exercises all of it.
"""

import json
import re
from io import BytesIO
from typing import Any
from xml.etree import ElementTree

from musibot.orchestrator_head import NameAndVersion, Pipeline, PipelineContext, Signature
from PIL import Image

IMAGE_FILE = "image.jpg"
LAYOUT_FILE = "layout.json"
TRANSCRIPTION_FILE = "transcription.musicxml"

STAFF_CATEGORY_ID = 0
"""What the *Musicorpus Specification* numbers a `staff` as. Fixed rather than
assigned per page, so that the same object is the same number in every
`layout.json` — see `components/models/dvorak-ola`, which writes the real ones."""

BYTE_COUNT = re.compile(r"\((\d+) bytes\)")
"""How `hello-model` reports what it read, inside the lyric of its one note."""


class HelloPipeline(Pipeline):
    """Runs `hello-model` and writes a `layout.json` with one made-up staff."""

    signature = Signature(input=[IMAGE_FILE], output=[LAYOUT_FILE, TRANSCRIPTION_FILE])
    """`transcription.musicxml` is declared even though this *Pipeline* does not
    write it: the *Model* it runs does, into the same page, and a *Signature*
    describes what an execution leaves behind rather than who put it there."""

    def __init__(self, name: str, version: str, *, model: NameAndVersion, margin: int = 20):
        self.name = name
        self.version = version

        self._model = model
        """Which *Model* to run, as a registration parameter. Registering this
        class a second time with a different pin is how one implementation
        becomes two *Pipelines*."""

        self._margin = margin
        """How far the made-up staff sits from each edge, in pixels."""

    async def execute(self, ctx: PipelineContext) -> None:
        ctx.logger.info("Running %s %s ...", self._model.name, self._model.version)
        await ctx.execute_model(self._model, input=[IMAGE_FILE])

        # What the Model wrote, read back out of the page. This is the whole
        # point of the exercise: a Pipeline learns what a Model did by reading
        # the Files it left behind, never from the result message.
        transcription = await ctx.read_text(TRANSCRIPTION_FILE)
        ctx.logger.info("The model read %d bytes of %s", byte_count(transcription), IMAGE_FILE)

        ctx.logger.info("Writing %s ...", LAYOUT_FILE)
        image = Image.open(BytesIO(await ctx.read_bytes(IMAGE_FILE)))
        await ctx.write_text(
            LAYOUT_FILE,
            json.dumps(layout_document(image.width, image.height, self._margin), indent=2),
        )

        ctx.logger.info("Done.")


def byte_count(transcription: str) -> int:
    """How many bytes `hello-model` said it read, out of its own MusicXML.

    Parsing a *Model's* output is a *Pipeline's* business and not Musibot's —
    to Musibot a *File* is opaque bytes. This one is pinned to a *Model* name
    and version, so it may rely on the shape of what that version writes, and
    say so plainly when it does not find it.
    """
    lyric = ElementTree.fromstring(transcription).find(".//lyric/text")
    match = BYTE_COUNT.search(lyric.text or "") if lyric is not None else None

    if match is None:
        raise ValueError(
            f"The model's {TRANSCRIPTION_FILE} does not say how many bytes it read, "
            f"so it is not the hello-model this pipeline is pinned to"
        )

    return int(match.group(1))


def layout_document(width: int, height: int, margin: int) -> dict[str, Any]:
    """A COCO `layout.json` holding one staff, inset from every edge.

    `layout.json` is a COCO object-detection document; the *Musicorpus
    Specification* defines it by analogy with `coco-object-detection.json`, with
    a vocabulary of page-structure objects instead of notation symbols.

    Nothing here is dated or randomised, so running this *Pipeline* twice over
    one page produces the same bytes — which makes the output diffable and a
    change to it visible.
    """
    box = (margin, margin, max(0, width - 2 * margin), max(0, height - 2 * margin))
    x, y, box_width, box_height = box

    return {
        "info": {
            "version": "1.0",
            "description": "A made-up staff, written by the Musibot hello-pipeline",
        },
        "images": [{"id": 0, "width": width, "height": height, "file_name": IMAGE_FILE}],
        "annotations": [
            {
                "id": 0,
                "image_id": 0,
                "category_id": STAFF_CATEGORY_ID,
                # Derived from the box, as the specification says it is for a
                # layout file: the area is the box's rather than a mask's, and
                # the segmentation is exactly the rectangle the box describes.
                "segmentation": [
                    [x, y, x, y + box_height, x + box_width, y + box_height, x + box_width, y]
                ],
                "area": box_width * box_height,
                "bbox": [x, y, box_width, box_height],
                "iscrowd": 0,
            }
        ],
        "categories": [{"id": STAFF_CATEGORY_ID, "name": "staff"}],
    }
