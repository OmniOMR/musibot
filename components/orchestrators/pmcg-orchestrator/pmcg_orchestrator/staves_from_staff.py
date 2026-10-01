"""Staff crops in, their transcriptions out: one *Model*, under a stable name.

Published as `mzk-staff`, around a Zeus snapshot. It does two things the
*Model's* own *ImplicitPipeline* does not.

**It keeps its name when the *Model* changes.** An *ImplicitPipeline* is called
after the *Model* behind it, so it is `ayce-long 2026-08-03-192253-final` today
and something else the day a better snapshot is deployed — nothing can be
written against it and stay written. `mzk-staff 1` does not move when the
snapshot does: the *Web UI* offers it beside `mzk-page`, and a *User* who pinned
it keeps getting the staff transcription it promised.

**It takes every staff of a page at once.** The *Model* reads one staff per
execution, which is right for it — one bad staff fails one execution and no
more. A *User* running the steps of `mzk-page` by hand, say to correct the
layout before anything is transcribed, would otherwise have to send one request
per staff; this runs the *Model* over every crop it is given, concurrently, and
reports the staves that failed rather than failing all of them.

There is no layout, no slicing and no gluing here: the *User* has done the
cutting, and `pmcg-glue` does the gluing.
"""

import asyncio

from musibot.orchestrator_head import (
    ModelExecutionFailed,
    NameAndVersion,
    Pipeline,
    PipelineContext,
    Signature,
)

from pmcg_orchestrator.steps import TRANSCRIPTION_FILE, spell

STAFF_IMAGES = "Staves/{*s}/image.jpg"
STAFF_TRANSCRIPTIONS = "Staves/{*s}/transcription.musicxml"
STAFF_LMX = "Staves/{*s}/transcription.lmx?"


class StavesFromStaffPipeline(Pipeline):
    """Staff-level transcription of any number of staves, by one named *Model*.

    Unversioned, unlike the other implementations here: it has no behaviour of
    its own beyond running the *Model*, so the version it is published under is
    the version of the choice of *Model*.
    """

    signature = Signature(input=[STAFF_IMAGES], output=[STAFF_TRANSCRIPTIONS, STAFF_LMX])
    """The transcription *Model's* own shape, widened from one staff to a set.
    One staff is still a valid set, which is what the *Web UI* sends: it uploads
    a single crop to `Staves/1/image.jpg`."""

    def __init__(self, name: str, version: str, *, staff_model: NameAndVersion):
        self.name = name
        self.version = version
        self._staff_model = staff_model

    async def execute(self, ctx: PipelineContext) -> None:
        images = sorted(ctx.input)
        if not images:
            raise ValueError("No staff images were given, so there is nothing to transcribe.")

        count = len(images)
        ctx.logger.info(
            "Transcribing %d %s with %s ...",
            count,
            "staff" if count == 1 else "staves",
            spell(self._staff_model),
        )

        outcomes = await asyncio.gather(
            *(self._transcribe(ctx, image) for image in images), return_exceptions=True
        )

        failures = [
            (image, outcome)
            for image, outcome in zip(images, outcomes)
            if isinstance(outcome, BaseException)
        ]
        for image, failure in failures:
            reason = str(failure) or type(failure).__name__
            ctx.logger.error("%s could not be transcribed: %s", image, reason)

        if len(failures) == count:
            if count == 1:
                # One staff is the whole request, and its own reason is the
                # most useful thing to tell the User.
                raise failures[0][1]
            raise ModelExecutionFailed(
                self._staff_model, f"none of the {count} staves could be transcribed"
            )

        if failures:
            ctx.logger.warning("Transcribed %d of %d staves.", count - len(failures), count)

        ctx.logger.info("Done.")

    async def _transcribe(self, ctx: PipelineContext, image: str) -> None:
        """One staff: run the *Model*, then check that it wrote something.

        Straight through: the *File* the *User* named is the *File* the *Model*
        is given, already checked by the `api` service against the *Signature*.
        A *Model* that reports success and writes nothing has failed this staff
        just as surely as one that reports a failure.
        """
        await ctx.execute_model(self._staff_model, input=[image])

        transcription = f"{image.rsplit('/', 1)[0]}/{TRANSCRIPTION_FILE}"
        if not await ctx.exists(transcription):
            raise ModelExecutionFailed(self._staff_model, f"it wrote no {transcription}")
