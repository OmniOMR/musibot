"""The steps several *Pipelines* share, each of them a few awaits against a page.

`mzk-page` does all of them in one execution; `pmcg-slice` and `pmcg-glue` each
do a part of that, for a *User* who wants to look at or correct what lies in
between. Sharing the steps is what keeps those pieces honest: slicing a page
with `pmcg-slice` produces exactly the crops `mzk-page` would have.
"""

import asyncio
import json
from typing import Any

from musibot.orchestrator_head import NameAndVersion, PipelineContext

from pmcg_orchestrator.errors import UnreadableLayout
from pmcg_orchestrator.layout import StaffBox
from pmcg_orchestrator.slicing import slice_page

IMAGE_FILE = "image.jpg"
LAYOUT_FILE = "layout.json"
TRANSCRIPTION_FILE = "transcription.musicxml"

STAFF_PADDING_RATIO = 0.9
"""How much of a staff's own height to add as a margin on every side when
cutting it out of the page. Proportional rather than a pixel count so that it
means the same thing at any scan resolution. A *Pipeline* that wants another
margin defines its own constant rather than changing this one, because every
*Pipeline* using it has promised its *Users* these crops."""


def staff_image(staff: int | str) -> str:
    return f"Staves/{staff}/{IMAGE_FILE}"


def staff_transcription(staff: int | str) -> str:
    return f"Staves/{staff}/{TRANSCRIPTION_FILE}"


def spell(model: NameAndVersion) -> str:
    """A *Model* as it appears in a log line the *User* reads."""
    return f"{model.name} {model.version}"


async def read_layout(ctx: PipelineContext) -> dict[str, Any]:
    """The page's `layout.json`, parsed."""
    try:
        layout: dict[str, Any] = json.loads(await ctx.read_text(LAYOUT_FILE))
    except json.JSONDecodeError as error:
        raise UnreadableLayout(f"The {LAYOUT_FILE} on this page is not JSON: {error}")

    if not isinstance(layout, dict):
        raise UnreadableLayout(f"The {LAYOUT_FILE} on this page is not a COCO document")

    return layout


def require_staves(ctx: PipelineContext, count: int) -> None:
    """Say how many staves the layout has, or fail if it has none."""
    if count == 0:
        # Not an internal error: an empty page, a cover, or a table of
        # contents is a page the layout model was trained for. There is
        # simply nothing here to work with, and saying so plainly beats
        # writing an empty result.
        raise ValueError("No staves were found on this page, so there is nothing to transcribe.")

    ctx.logger.info("Found %d staves.", count)


async def slice_into_staves(
    ctx: PipelineContext, boxes: list[StaffBox], padding_ratio: float
) -> None:
    """Cut `image.jpg` into `Staves/<n>/image.jpg`, `n` being each box's number."""
    ctx.logger.info("Slicing the page into %d staff images ...", len(boxes))

    page = await ctx.read_bytes(IMAGE_FILE)
    # OpenCV is blocking CPU work and this process runs several executions at
    # once, so the whole page is sliced in one hop off the event loop rather
    # than one per staff.
    crops = await asyncio.to_thread(slice_page, page, boxes, padding_ratio)

    # Named by the box's own number rather than by its position in this list,
    # because that number is what the gluing looks the staff up by.
    for box, crop in zip(boxes, crops, strict=True):
        await ctx.write_bytes(staff_image(box.number), crop)
