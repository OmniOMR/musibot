"""The *Orchestrator* holding the OmniOMR project's *Pipelines*.

Two of them, and they are the two things a *User* arrives with:

- `mzk-page` — a page scan in, a page-level MusicXML file out.
- `mzk-staff` — one staff crop in, its transcription out.

Which *Models* they run, and under what names and versions they are announced,
are all settings — so the *Pipeline* being developed is this same program
started with different ones:

    musibot-omniomr-orchestrator \\
        --page-pipeline-name mzk-page-dev --page-pipeline-version 2 \\
        --staff-pipeline-name mzk-staff-dev --staff-pipeline-version 2 \\
        --staff-model 'ayce-long@2026-08-14-something-newer'

Both processes may run against one Musibot at the same time. They announce
different *Pipelines*, so a *User* chooses between them by name, and neither
takes the other's work.
"""

from musibot.orchestrator_head import NameAndVersion, Orchestrator, OrchestratorHeadSettings
from pydantic import field_validator

from omniomr_orchestrator.page import MzkPagePipeline
from omniomr_orchestrator.staff import MzkStaffPipeline

__all__ = ["MzkPagePipeline", "MzkStaffPipeline", "OmniOmrSettings", "main"]

ORCHESTRATOR_NAME = "omniomr"

MODEL_REFERENCE_SEPARATOR = "@"
"""How a *Model* is written in one setting — `name@version`, the same spelling
routing keys and queue names use."""


def model_reference(reference: str) -> NameAndVersion:
    """Read `name@version` into the pair Musibot addresses work with."""
    name, separator, version = reference.partition(MODEL_REFERENCE_SEPARATOR)
    if not separator or not name or not version:
        raise ValueError(f"A model is written name@version, not {reference!r}")
    return NameAndVersion(name=name, version=version)


class OmniOmrSettings(OrchestratorHeadSettings):
    """What this *Orchestrator* is configured with, beyond the shared blocks.

    The defaults are the *Models* the development stack currently runs, so that
    this starts with no arguments against it — as every other Musibot service
    does. **A deployment pins all four explicitly**, because a snapshot that has
    been superseded is exactly the kind of thing a default quietly keeps
    pointing at.
    """

    page_pipeline_name: str = "mzk-page"
    """What the page-level *Pipeline* is announced as. The *Web UI* offers this
    name and version by default, so changing either here hides it from the
    landing page — which is exactly what a development deployment wants."""

    page_pipeline_version: str = "1"
    """Bumped when the *Pipeline* would transcribe the same page differently —
    a new *Model* snapshot, or a change to the slicing or the concatenation.
    An opaque string to Musibot, plain integers here."""

    staff_pipeline_name: str = "mzk-staff"
    """And the staff-level one, which the *Web UI* also offers by default."""

    staff_pipeline_version: str = "1"

    layout_model: str = "dvorak-ola@2.0-2025-03-09"
    """The *Model* that finds the staves, as `name@version`."""

    staff_model: str = "ayce-long@2026-08-03-192253-final"
    """The *Model* that transcribes one staff, as `name@version`. This is the
    setting a development deployment usually changes."""

    staff_padding_ratio: float = 0.9
    """How much of a staff's own height to add as a margin on every side when
    cutting it out of the page. Proportional rather than a pixel count so that
    it means the same thing at any scan resolution."""

    layout_confidence: float | None = None
    """Passed to the layout *Model* as its `confidence` parameter. Unset leaves
    that *Model's* own default alone, which is the right thing to do until
    there is a reason not to."""

    @field_validator("layout_model", "staff_model")
    @classmethod
    def _is_a_model_reference(cls, value: str) -> str:
        # Checked while the settings load, so a typo stops the process at
        # startup with a legible message rather than becoming a Pipeline that
        # announces itself and then times out every execution.
        model_reference(value)
        return value


def main() -> None:
    """Run the OmniOMR orchestrator until it is stopped."""
    settings = OmniOmrSettings.load()

    layout_model = model_reference(settings.layout_model)
    staff_model = model_reference(settings.staff_model)

    orchestrator = Orchestrator(ORCHESTRATOR_NAME, settings)
    orchestrator.register_pipeline(
        MzkPagePipeline(
            settings.page_pipeline_name,
            settings.page_pipeline_version,
            layout_model=layout_model,
            staff_model=staff_model,
            staff_padding_ratio=settings.staff_padding_ratio,
            layout_confidence=settings.layout_confidence,
        )
    )
    orchestrator.register_pipeline(
        MzkStaffPipeline(
            settings.staff_pipeline_name,
            settings.staff_pipeline_version,
            staff_model=staff_model,
        )
    )
    orchestrator.run()
