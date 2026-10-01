"""The `mzk-staff` pipeline: one staff crop in, its transcription out.

It runs the transcription *Model* on the *File* it was given and does nothing
else — no layout, no slicing, no concatenation, because the *User* has already
done the cutting.

Which makes it, step for step, what the *Model's* own *ImplicitPipeline* does.
It exists anyway, and the reason is the name. An *ImplicitPipeline* is called
after the *Model* behind it, so it is `ayce-long 2026-08-03-192253-final` today
and something else the day a better snapshot is deployed — nothing can be
written against it and stay written. `mzk-staff 1` does not move when the
snapshot does: the *Web UI* offers it beside `mzk-page`, and a *User* who pinned
it keeps getting the staff transcription this project recommends rather than
whichever *Model* happens to be running.
"""

from musibot.orchestrator_head import NameAndVersion, Pipeline, PipelineContext, Signature

STAFF_IMAGE = "Staves/{s}/image.jpg"
STAFF_TRANSCRIPTION = "Staves/{s}/transcription.musicxml"
STAFF_LMX = "Staves/{s}/transcription.lmx?"


class MzkStaffPipeline(Pipeline):
    """Staff-level transcription: the recommended *Model*, under a stable name."""

    signature = Signature(input=[STAFF_IMAGE], output=[STAFF_TRANSCRIPTION, STAFF_LMX])
    """The transcription *Model's* own shape, repeated. `{s}` is one staff per
    execution, which is what makes a failure a failure of that staff and no
    more, and it is what tells the *Web UI* to upload to `Staves/1/image.jpg`
    rather than to `image.jpg`."""

    def __init__(self, name: str, version: str, *, staff_model: NameAndVersion):
        self.name = name
        self.version = version
        self._staff_model = staff_model

    async def execute(self, ctx: PipelineContext) -> None:
        ctx.logger.info(
            "Transcribing %s with %s %s ...",
            ", ".join(ctx.input),
            self._staff_model.name,
            self._staff_model.version,
        )

        # Straight through. The *Files* the *User* named are the *Files* the
        # *Model* is given — the `api` service has already checked them against
        # the *Signature* above, which is the *Model's* own.
        await ctx.execute_model(self._staff_model, input=list(ctx.input))

        ctx.logger.info("Done.")
