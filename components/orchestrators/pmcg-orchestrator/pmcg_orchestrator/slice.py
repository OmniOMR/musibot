"""A page and its layout in, one crop per staff out.

Published as `pmcg-slice`. It is step 2 of `mzk-page` on its own, for a *User*
running those steps by hand — typically to correct `layout.json` before
anything is transcribed — and it cuts exactly the crops `mzk-page` would have,
because both use `pmcg_orchestrator.steps`.

The staves are numbered `Staves/1` to `Staves/N` in reading order: top to
bottom, and left to right between staves at the same height. That numbering is
what `pmcg-glue` later pairs the staff transcriptions with the layout by.
"""

from musibot.orchestrator_head import Pipeline, PipelineContext, Signature

from pmcg_orchestrator.layout import staff_boxes
from pmcg_orchestrator.steps import (
    IMAGE_FILE,
    LAYOUT_FILE,
    STAFF_PADDING_RATIO,
    read_layout,
    require_staves,
    slice_into_staves,
)


class SlicePipelineV1(Pipeline):
    """Staff crops out of a page, a rectangle per `staff` box plus a margin."""

    signature = Signature(input=[IMAGE_FILE, LAYOUT_FILE], output=["Staves/{*}/image.jpg"])

    STAFF_PADDING_RATIO = STAFF_PADDING_RATIO
    """The margin around each crop, as a fraction of the staff's own height."""

    def __init__(self, name: str, version: str):
        self.name = name
        self.version = version

    async def execute(self, ctx: PipelineContext) -> None:
        ctx.logger.info("Reading the staves out of %s ...", LAYOUT_FILE)
        boxes = staff_boxes(await read_layout(ctx))
        require_staves(ctx, len(boxes))

        await slice_into_staves(ctx, boxes, self.STAFF_PADDING_RATIO)
        ctx.logger.info("Done.")
