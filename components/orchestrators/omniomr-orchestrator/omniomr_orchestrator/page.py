"""The `mzk-page` pipeline: a page scan in, a page-level MusicXML file out.

Four steps, and the *User* is told about each of them as it happens:

1. a layout *Model* finds the staves,
2. this cuts the page into one crop per staff,
3. a transcription *Model* reads each crop, all of them at once,
4. this glues the results into one document, a system per staff.

Steps 1 and 3 are *Models* and could be anything — which two is a registration
parameter, because that is what makes this implementation deployable twice, once
against the snapshots production uses and once against the ones being developed.
Steps 2 and 4 are this *Pipeline's* own work and are the parts that will move
into a Musicorpus library when there is one.

The version number in the *Pipeline's* name is not decoration. Both of this
version's own steps are deliberately naive — see the README — and improving
either produces a different transcription of the same page, which is exactly
what a *User* pinning a version is protecting themselves from.
"""

import asyncio
import json

from musibot.orchestrator_head import (
    ModelExecutionFailed,
    NameAndVersion,
    Pipeline,
    PipelineContext,
    Signature,
)

from omniomr_orchestrator.layout import StaffBox, UnreadableLayout, staff_boxes
from omniomr_orchestrator.musicxml import StaffTranscription, page_musicxml
from omniomr_orchestrator.slicing import slice_page

IMAGE_FILE = "image.jpg"
LAYOUT_FILE = "layout.json"
TRANSCRIPTION_FILE = "transcription.musicxml"


def staff_image(number: int) -> str:
    return f"Staves/{number}/{IMAGE_FILE}"


def staff_transcription(number: int) -> str:
    return f"Staves/{number}/{TRANSCRIPTION_FILE}"


class MzkPagePipeline(Pipeline):
    """Page-level image-to-MusicXML transcription."""

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

    def __init__(
        self,
        name: str,
        version: str,
        *,
        layout_model: NameAndVersion,
        staff_model: NameAndVersion,
        staff_padding_ratio: float = 0.9,
        layout_confidence: float | None = None,
    ):
        self.name = name
        self.version = version

        self._layout_model = layout_model
        self._staff_model = staff_model
        self._staff_padding_ratio = staff_padding_ratio
        self._layout_confidence = layout_confidence

    async def execute(self, ctx: PipelineContext) -> None:
        boxes = await self._detect_staves(ctx)
        await self._slice_page(ctx, boxes)

        staves = await self._transcribe_staves(ctx, len(boxes))

        ctx.logger.info("Writing %s ...", TRANSCRIPTION_FILE)
        await ctx.write_text(TRANSCRIPTION_FILE, page_musicxml(staves))
        ctx.logger.info("Done.")

    # --- 1. the staves -------------------------------------------------------

    async def _detect_staves(self, ctx: PipelineContext) -> list[StaffBox]:
        ctx.logger.info("Detecting staves with %s ...", _spell(self._layout_model))

        parameters: dict[str, object] = {}
        if self._layout_confidence is not None:
            # The layout model's own knob, rather than a threshold applied to
            # its output here: dropping a detection before it is made is the
            # same answer for less work, and the model documents the default.
            parameters["confidence"] = self._layout_confidence

        await ctx.execute_model(self._layout_model, input=[IMAGE_FILE], parameters=parameters)

        try:
            layout = json.loads(await ctx.read_text(LAYOUT_FILE))
        except json.JSONDecodeError as error:
            raise UnreadableLayout(
                f"The layout model wrote a {LAYOUT_FILE} that is not JSON: {error}"
            )

        boxes = staff_boxes(layout)

        if not boxes:
            # Not an internal error: an empty page, a cover, or a table of
            # contents is a page the layout model was trained for. There is
            # simply nothing here to transcribe, and saying so plainly beats
            # writing an empty score.
            raise ValueError(
                "No staves were found on this page, so there is nothing to transcribe."
            )

        ctx.logger.info("Found %d staves.", len(boxes))
        return boxes

    # --- 2. the crops --------------------------------------------------------

    async def _slice_page(self, ctx: PipelineContext, boxes: list[StaffBox]) -> None:
        ctx.logger.info("Slicing the page into %d staff images ...", len(boxes))

        page = await ctx.read_bytes(IMAGE_FILE)
        # OpenCV is blocking CPU work and this process runs several executions
        # at once, so the whole page is sliced in one hop off the event loop
        # rather than one per staff.
        crops = await asyncio.to_thread(slice_page, page, boxes, self._staff_padding_ratio)

        for number, crop in enumerate(crops, start=1):
            await ctx.write_bytes(staff_image(number), crop)

    # --- 3. the transcriptions -----------------------------------------------

    async def _transcribe_staves(
        self, ctx: PipelineContext, count: int
    ) -> list[StaffTranscription]:
        """Run the transcription *Model* over every staff, at once.

        One failed staff does not fail the page. A scan of a real book has
        stains, cropped systems and pages the detector was too generous about,
        and returning eleven staves of a twelve-staff page is far more useful to
        a *User* than returning an error — so failures are gathered, said in the
        log, and become empty parts. A page where *every* staff failed is a
        different thing and does fail.
        """
        ctx.logger.info("Transcribing %d staves with %s ...", count, _spell(self._staff_model))

        numbers = range(1, count + 1)
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


def _spell(model: NameAndVersion) -> str:
    """A *Model* as it appears in a log line the *User* reads."""
    return f"{model.name} {model.version}"
