"""The two *Models* the `mzk` pipeline runs, faked well enough to be worth it.

Both write what the real ones write — a COCO layout document, and MusicXML with
measures in it — so that what the tests exercise is this pipeline's parsing,
arithmetic and concatenation rather than a mock agreeing with itself.
"""

import json
from typing import Any

import cv2
import numpy as np
from musibot.orchestrator_head import NameAndVersion
from musibot.orchestrator_head.testing import ModelCall, PipelineRunner

LAYOUT_MODEL = NameAndVersion(name="dvorak-ola", version="2.0-2025-03-09")
STAFF_MODEL = NameAndVersion(name="ayce-long", version="2026-08-03-192253-final")

PAGE_WIDTH = 400
PAGE_HEIGHT = 300

STAFF_CATEGORY_ID = 0


def a_page(width: int = PAGE_WIDTH, height: int = PAGE_HEIGHT) -> bytes:
    """A page scan: white, with a black line where each staff will be cut."""
    page = np.full((height, width, 3), 255, dtype=np.uint8)
    written, buffer = cv2.imencode(".jpg", page)
    assert written
    return bytes(buffer)


def a_layout(*boxes: tuple[int, int, int, int], categories: bool = True) -> bytes:
    """A COCO `layout.json` naming those staves, as dvorak-ola writes one."""
    document: dict[str, Any] = {
        "info": {"description": "a fake"},
        "images": [{"id": 0, "width": PAGE_WIDTH, "height": PAGE_HEIGHT, "file_name": "image.jpg"}],
        "annotations": [
            {
                "id": index,
                "image_id": 0,
                "category_id": STAFF_CATEGORY_ID,
                "bbox": list(box),
                "area": box[2] * box[3],
                "iscrowd": 0,
                "score": 0.9,
            }
            for index, box in enumerate(boxes)
        ],
        "categories": ([{"id": STAFF_CATEGORY_ID, "name": "staff"}] if categories else []),
    }
    return json.dumps(document).encode("utf-8")


def a_staff_transcription(text: str = "one measure", measures: int = 1) -> str:
    """What a staff transcription model writes: one part, numbering its own
    measures from 1 — which is why the page has to renumber them."""
    written = "\n".join(
        f"""    <measure number="{number}">
      <attributes><divisions>1</divisions></attributes>
      <note><rest measure="yes"/><duration>4</duration><lyric><text>{text}</text></lyric></note>
    </measure>"""
        for number in range(1, measures + 1)
    )
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<score-partwise version="4.0">
  <part-list>
    <score-part id="P1"><part-name>Staff</part-name></score-part>
  </part-list>
  <part id="P1">
{written}
  </part>
</score-partwise>
"""


def writes_layout(*boxes: tuple[int, int, int, int]) -> Any:
    """A layout model that reports exactly these staves."""

    def behaviour(call: ModelCall, files: dict[str, bytes]) -> None:
        files["layout.json"] = a_layout(*boxes)

    return behaviour


def transcribes_every_staff(call: ModelCall, files: dict[str, bytes]) -> None:
    """A staff model that transcribes whatever crop it is handed.

    It writes beside its input, exactly as a `Staves/{s}` model does, and names
    the crop's size so a test can tell the staves apart.
    """
    [staff_image] = call.input
    crop = cv2.imdecode(np.frombuffer(files[staff_image], dtype=np.uint8), cv2.IMREAD_COLOR)
    assert crop is not None, f"the pipeline wrote a {staff_image} that is not an image"
    height, width = crop.shape[:2]

    folder = staff_image.rsplit("/", 1)[0]
    files[f"{folder}/transcription.musicxml"] = a_staff_transcription(f"{width}x{height}").encode(
        "utf-8"
    )


def fails_staff(number: int, reason: str = "The model could not read this staff.") -> Any:
    """A staff model that fails one particular staff and transcribes the rest."""

    def behaviour(call: ModelCall, files: dict[str, bytes]) -> None:
        if call.input == [f"Staves/{number}/image.jpg"]:
            raise RuntimeError(reason)
        transcribes_every_staff(call, files)

    return behaviour


def a_runner(*boxes: tuple[int, int, int, int], staff_model: Any = None) -> PipelineRunner:
    """A runner with a page, a layout model and a staff model already in it."""
    runner = PipelineRunner({"image.jpg": a_page()})
    runner.register_model(LAYOUT_MODEL, writes_layout(*boxes))
    runner.register_model(STAFF_MODEL, staff_model or transcribes_every_staff)
    return runner
