"""A layout and its staff transcriptions in, one page-level MusicXML file out.

Published as `pmcg-glue`, in two versions that are the two gluings `mzk-page`
has had: version 1 writes the page as one instrument, version 2 as a part per
instrument — see `pmcg_orchestrator.gluing`. It is step 4 of `mzk-page` on its
own, for a *User* running those steps by hand.

**How staves are paired with the layout.** `layout.json` has boxes and no
names, while the staves have names and no boxes, so they are paired by order:

- Staff folder names must be integers. They need not be contiguous — the
  *Musicorpus Specification* numbers every staff down the page, empty ones
  included, while the layout marks empty staves with a category of their own —
  so `Staves/1`, `Staves/2`, `Staves/4` is a perfectly good page.
- The staff images name the set of staves; nothing is read out of them. A
  staff with an image and no transcription is one that failed, and becomes a
  placeholder in the score, exactly as it would in `mzk-page`.
- The staves, sorted by number, are paired one to one with the layout's `staff`
  boxes in reading order, top to bottom. If the counts differ, as many are
  paired as can be, from the top, and the rest on either side are left out and
  said in the log.

`pmcg-slice` numbers its crops `1` to `N` in exactly that reading order, so its
output pairs up with no gaps.
"""

import re

from musibot.orchestrator_head import Pipeline, PipelineContext, Signature

from pmcg_orchestrator.gluing import StaffTranscription
from pmcg_orchestrator.gluing import v1 as gluing_v1
from pmcg_orchestrator.gluing import v2 as gluing_v2
from pmcg_orchestrator.layout import keep_first_staves, layout_to_instruments, staff_boxes
from pmcg_orchestrator.steps import (
    IMAGE_FILE,
    LAYOUT_FILE,
    TRANSCRIPTION_FILE,
    read_layout,
    staff_transcription,
)

STAFF_FILE = re.compile(r"^Staves/(?P<staff>[^/]+)/(?P<file>[^/]+)$")


class GluePipeline(Pipeline):
    """The pairing every version shares. A version's `execute` does the gluing."""

    signature = Signature(
        input=[LAYOUT_FILE, "Staves/{*}/image.jpg", "Staves/{*}/transcription.musicxml"],
        output=[TRANSCRIPTION_FILE],
    )
    """The two `{*}` are deliberately unrelated: a staff may have an image and no
    transcription, which is a staff that failed rather than a malformed request."""

    def __init__(self, name: str, version: str):
        self.name = name
        self.version = version

    def _staves(self, ctx: PipelineContext) -> list[int]:
        """The staff numbers this page has, from the images it was given, in order."""
        staves = sorted(_staff_folders(ctx.input, IMAGE_FILE))

        orphans = sorted(set(_staff_folders(ctx.input, TRANSCRIPTION_FILE)) - set(staves))
        if orphans:
            ctx.logger.warning(
                "Ignoring the transcriptions of staves %s, which have no staff image.",
                ", ".join(map(str, orphans)),
            )

        return staves

    def _pair(self, ctx: PipelineContext, staves: list[int], box_count: int) -> list[int]:
        """The staves that get a layout box, in reading order. Says what is left out."""
        if len(staves) > box_count:
            ctx.logger.warning(
                "The layout has %d staves and %d staff images were given; leaving out staves %s.",
                box_count,
                len(staves),
                ", ".join(map(str, staves[box_count:])),
            )
        elif len(staves) < box_count:
            ctx.logger.warning(
                "The layout has %d staves and %d staff images were given; "
                "leaving out the bottom %d of the layout's staves.",
                box_count,
                len(staves),
                box_count - len(staves),
            )

        return staves[:box_count]

    async def _read_transcriptions(
        self, ctx: PipelineContext, staves: list[int], numbers: list[int]
    ) -> list[StaffTranscription]:
        """Each of `staves`' transcriptions, labelled with the matching `numbers`.

        A staff with no transcription is a staff that failed, and comes back as
        such. A page where none of them has one fails, since there would be
        nothing in the score but placeholders.
        """
        given = _staff_folders(ctx.input, TRANSCRIPTION_FILE)
        if not given.keys() & set(staves):
            raise ValueError(
                f"None of the {len(staves)} staves has a transcription, so there is nothing "
                "to glue."
            )

        transcriptions: list[StaffTranscription] = []
        for staff, number in zip(staves, numbers, strict=True):
            if staff in given:
                musicxml = await ctx.read_text(staff_transcription(given[staff]))
                transcriptions.append(StaffTranscription(number=number, musicxml=musicxml))
            else:
                ctx.logger.error("Staff %d has no transcription.", staff)
                transcriptions.append(StaffTranscription(number=number, error="no transcription"))

        return transcriptions

    async def _write_page(self, ctx: PipelineContext, musicxml: str) -> None:
        ctx.logger.info("Writing %s ...", TRANSCRIPTION_FILE)
        await ctx.write_text(TRANSCRIPTION_FILE, musicxml)
        ctx.logger.info("Done.")


class GluePipelineV1(GluePipeline):
    """Every staff's measures into one `<part>`, one staff after another."""

    async def execute(self, ctx: PipelineContext) -> None:
        staves = self._staves(ctx)
        box_count = len(staff_boxes(await read_layout(ctx)))
        staves = self._pair(ctx, staves, box_count)
        _require_staves(staves)

        ctx.logger.info("Gluing %d staves into one part ...", len(staves))
        # Labelled with the staff's own number, which is what a placeholder in
        # the score says: the layout's boxes play no further part here.
        transcriptions = await self._read_transcriptions(ctx, staves, staves)

        await self._write_page(ctx, gluing_v1.glue(transcriptions))


class GluePipelineV2(GluePipeline):
    """A `<part>` per instrument, as the layout's systems and grand staves say."""

    async def execute(self, ctx: PipelineContext) -> None:
        staves = self._staves(ctx)
        layout = await read_layout(ctx)
        staves = self._pair(ctx, staves, len(staff_boxes(layout)))
        _require_staves(staves)

        # Staves of the layout with no image to pair with are dropped from it,
        # so the instruments are worked out from the staves there is music for.
        page_layout = layout_to_instruments(keep_first_staves(layout, len(staves)))
        ctx.logger.info("Ordered staves into instruments: %s", str(page_layout))

        ctx.logger.info(
            "Gluing %d staves into %d parts ...", len(staves), len(page_layout.instruments)
        )
        # Labelled with the layout's own staff numbers, which version 2 looks
        # each staff up by.
        numbers = [box.number for box in page_layout.get_all_staffs()]
        transcriptions = await self._read_transcriptions(ctx, staves, sorted(numbers))

        await self._write_page(ctx, gluing_v2.glue(ctx, transcriptions, page_layout))


def _staff_folders(paths: list[str], file_name: str) -> dict[int, str]:
    """The staff folders among `paths` holding `file_name`, by their number."""
    folders: dict[int, str] = {}
    for path in paths:
        match = STAFF_FILE.match(path)
        if match is None or match["file"] != file_name:
            continue

        staff = match["staff"]
        if not staff.isdigit():
            raise ValueError(
                f"Staff folders are paired with the layout by number, and {staff!r} "
                f"(in {path}) is not one."
            )

        number = int(staff)
        if number in folders:
            raise ValueError(
                f"Staff folders {folders[number]!r} and {staff!r} are the same number, "
                "so they cannot be told apart in the layout."
            )
        folders[number] = staff
    return folders


def _require_staves(staves: list[int]) -> None:
    if not staves:
        raise ValueError(
            "There are no staves to glue: either the layout has none, or no staff images were "
            "given."
        )
