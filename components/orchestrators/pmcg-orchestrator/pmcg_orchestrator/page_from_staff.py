"""A page scan in, a page-level MusicXML file out, by way of staff-level transcription.

Published as `mzk-page`, around dvorak-ola and a Zeus snapshot, but nothing in
it is particular to those *Models* or to the MZK. Four steps, and the *User* is
told about each of them as it happens:

1. a layout *Model* finds the staves,
2. this cuts the page into one crop per staff,
3. a staff transcription *Model* reads each crop, all of them at once,
4. this glues the results into one document.

Steps 1 and 3 are *Models* and could be anything — which two is a constructor
argument, so that the same implementation can be published again around other
*Models*. Which ones a published *Pipeline* runs is written down where it is
registered, in `pmcg_orchestrator.registered_pipelines`. Steps 2 and 4 are this
*Pipeline's* own work and are the parts that will move into a Musicorpus
library when there is one.

The two versions differ in how much of the layout they read and in how they
glue: version 1 reads only the staves and writes the page as one instrument,
version 2 reads systems and grand staves too and writes a part per instrument.
Everything else is the shared base class. A class's version is the version of
the gluing it does — see `pmcg_orchestrator.gluing` — and is independent of the
version it is published under, though the two coincide for `mzk-page`.
"""

import asyncio
import json
from typing import Any

from musibot.orchestrator_head import (
    ModelExecutionFailed,
    NameAndVersion,
    Pipeline,
    PipelineContext,
    Signature,
)

from pmcg_orchestrator.errors import UnreadableLayout
from pmcg_orchestrator.gluing import StaffTranscription
from pmcg_orchestrator.gluing import v1 as gluing_v1
from pmcg_orchestrator.gluing import v2 as gluing_v2
from pmcg_orchestrator.layout import (
    RETRIEVED_LAYOUT_CATEGORIES,
    StaffBox,
    layout_to_instruments,
    staff_boxes,
)
from pmcg_orchestrator.slicing import slice_page

IMAGE_FILE = "image.jpg"
LAYOUT_FILE = "layout.json"
TRANSCRIPTION_FILE = "transcription.musicxml"


def staff_image(number: int) -> str:
    return f"Staves/{number}/{IMAGE_FILE}"


def staff_transcription(number: int) -> str:
    return f"Staves/{number}/{TRANSCRIPTION_FILE}"


class PageFromStaffPipeline(Pipeline):
    """The steps every version shares. A version's `execute` strings them together."""

    signature = Signature(
        input=[IMAGE_FILE],
        output=[
            LAYOUT_FILE,
            "Staves/{*s}/image.jpg",
            "Staves/{*s}/transcription.musicxml",
            # Zeus writes one beside every transcription; another transcription
            # Model need not, so it is declared optional rather than promised.
            "Staves/{*s}/transcription.lmx?",
            TRANSCRIPTION_FILE,
        ],
    )
    """Everything the execution leaves behind, not only the final file. The
    staff crops and their transcriptions stay in the page deliberately: they are
    what somebody looks at when the result is wrong, and a *MusicorpusPage* is
    thrown away in a few minutes anyway."""

    STAFF_PADDING_RATIO = 0.9
    """How much of a staff's own height to add as a margin on every side when
    cutting it out of the page. Proportional rather than a pixel count so that
    it means the same thing at any scan resolution. Part of what this
    implementation does to a page, so not a parameter."""

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

    # --- 1. the layout -------------------------------------------------------

    async def _detect_layout(self, ctx: PipelineContext, looking_for: str) -> dict[str, Any]:
        """Run the layout *Model* and read the document it wrote."""
        ctx.logger.info("Detecting %s with %s ...", looking_for, _spell(self._layout_model))

        await ctx.execute_model(self._layout_model, input=[IMAGE_FILE])

        try:
            layout: dict[str, Any] = json.loads(await ctx.read_text(LAYOUT_FILE))
        except json.JSONDecodeError as error:
            raise UnreadableLayout(
                f"The layout model wrote a {LAYOUT_FILE} that is not JSON: {error}"
            )

        return layout

    def _require_staves(self, ctx: PipelineContext, count: int) -> None:
        if count == 0:
            # Not an internal error: an empty page, a cover, or a table of
            # contents is a page the layout model was trained for. There is
            # simply nothing here to transcribe, and saying so plainly beats
            # writing an empty score.
            raise ValueError(
                "No staves were found on this page, so there is nothing to transcribe."
            )

        ctx.logger.info("Found %d staves.", count)

    # --- 2. the crops --------------------------------------------------------

    async def _slice_page(self, ctx: PipelineContext, boxes: list[StaffBox]) -> None:
        ctx.logger.info("Slicing the page into %d staff images ...", len(boxes))

        page = await ctx.read_bytes(IMAGE_FILE)
        # OpenCV is blocking CPU work and this process runs several executions
        # at once, so the whole page is sliced in one hop off the event loop
        # rather than one per staff.
        crops = await asyncio.to_thread(slice_page, page, boxes, self.STAFF_PADDING_RATIO)

        # Named by the box's own number rather than by its position in this
        # list, because that number is what the gluing looks the staff up by.
        for box, crop in zip(boxes, crops, strict=True):
            await ctx.write_bytes(staff_image(box.number), crop)

    # --- 3. the transcriptions -----------------------------------------------

    async def _transcribe_staves(
        self, ctx: PipelineContext, boxes: list[StaffBox]
    ) -> list[StaffTranscription]:
        """Run the transcription *Model* over every staff, at once.

        One failed staff does not fail the page. A scan of a real book has
        stains, cropped systems and pages the detector was too generous about,
        and returning eleven staves of a twelve-staff page is far more useful to
        a *User* than returning an error — so failures are gathered, said in the
        log, and become placeholders in the score. A page where *every* staff
        failed is a different thing and does fail.
        """
        count = len(boxes)
        ctx.logger.info("Transcribing %d staves with %s ...", count, _spell(self._staff_model))

        numbers = sorted(box.number for box in boxes)
        outcomes = await asyncio.gather(
            *(self._transcribe_staff(ctx, number) for number in numbers),
            return_exceptions=True,
        )

        staves: list[StaffTranscription] = []
        for number, outcome in zip(numbers, outcomes):
            if isinstance(outcome, BaseException):
                reason = str(outcome) or type(outcome).__name__
                ctx.logger.error("Staff %d could not be transcribed: %s", number, reason)
                staves.append(StaffTranscription(number=number, error=reason))
            else:
                staves.append(StaffTranscription(number=number, musicxml=outcome))

        transcribed = sum(1 for staff in staves if staff.transcribed)
        if transcribed == 0:
            raise ModelExecutionFailed(
                self._staff_model, f"none of the {count} staves on this page could be transcribed"
            )

        if transcribed < count:
            ctx.logger.warning("Transcribed %d of %d staves.", transcribed, count)

        return staves

    async def _transcribe_staff(self, ctx: PipelineContext, number: int) -> str:
        """One staff: run the *Model*, then read what it wrote.

        Reading is part of the same step because a *Model* that reports success
        and writes nothing has failed this staff just as surely as one that
        reports a failure, and the caller should not have to tell them apart.
        """
        await ctx.execute_model(self._staff_model, input=[staff_image(number)])
        return await ctx.read_text(staff_transcription(number))

    # --- 4. the page ---------------------------------------------------------

    async def _write_page(self, ctx: PipelineContext, musicxml: str) -> None:
        ctx.logger.info("Writing %s ...", TRANSCRIPTION_FILE)
        await ctx.write_text(TRANSCRIPTION_FILE, musicxml)
        ctx.logger.info("Done.")


class PageFromStaffPipelineV1(PageFromStaffPipeline):
    """Page-level transcription, the page read as one instrument.

    Only the `staff` boxes are read, and every staff's measures go into one
    `<part>` with a system break where each staff begins — see
    `pmcg_orchestrator.gluing.v1`.
    """

    async def execute(self, ctx: PipelineContext) -> None:
        layout = await self._detect_layout(ctx, "staves")
        boxes = staff_boxes(layout)
        self._require_staves(ctx, len(boxes))

        await self._slice_page(ctx, boxes)
        staves = await self._transcribe_staves(ctx, boxes)

        await self._write_page(ctx, gluing_v1.glue(staves))


class PageFromStaffPipelineV2(PageFromStaffPipeline):
    """Page-level transcription, a part per instrument.

    The `system` and `grandstaff` boxes are read too, to group the staves into
    instruments — see `pmcg_orchestrator.gluing.v2`.
    """

    async def execute(self, ctx: PipelineContext) -> None:
        layout = await self._detect_layout(ctx, ",".join(sorted(RETRIEVED_LAYOUT_CATEGORIES)))
        page_layout = layout_to_instruments(layout)
        self._require_staves(ctx, page_layout.staff_count)
        ctx.logger.info("Ordered staves into instruments: %s", str(page_layout))

        boxes = page_layout.get_all_staffs()
        await self._slice_page(ctx, boxes)
        staves = await self._transcribe_staves(ctx, boxes)

        await self._write_page(ctx, gluing_v2.glue(ctx, staves, page_layout))


def _spell(model: NameAndVersion) -> str:
    """A *Model* as it appears in a log line the *User* reads."""
    return f"{model.name} {model.version}"
