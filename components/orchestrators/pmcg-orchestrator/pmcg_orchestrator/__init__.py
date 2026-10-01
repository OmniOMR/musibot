"""The *Orchestrator* holding the Prague Music Computing Group's *Pipelines*.

A *Pipeline's* name and version are a contract with the *User* about how it
behaves, so everything that decides that behaviour is written down here in the
source — which implementation, which *Models* it runs, under what name and
version it is announced — and none of it is configuration. Changing any of it
is a change to this program and a re-deployment, and whether the published
version moves with it depends on how much the behaviour does.

`registered_pipelines` is that contract, one registration per published
*Pipeline*. An implementation class may appear in it more than once, with
different *Models*, under different names.
"""

from collections.abc import Sequence

from pydantic import Field
from musibot.orchestrator_head import (
    NameAndVersion,
    Orchestrator,
    OrchestratorHeadSettings,
    Pipeline,
)

from pmcg_orchestrator.page_from_staff import PageFromStaffPipelineV1, PageFromStaffPipelineV2
from pmcg_orchestrator.staff import MzkStaffPipeline

__all__ = ["PmcgSettings", "main", "registered_pipelines", "selected_pipelines"]

ORCHESTRATOR_NAME = "pmcg"

DVORAK_OLA = NameAndVersion(name="dvorak-ola", version="2.0-2025-03-09")
"""The layout *Model* that finds the staves, systems and grand staves."""

AYCE_LONG = NameAndVersion(name="ayce-long", version="2026-08-03-192253-final")
"""The Zeus snapshot that transcribes one staff."""

PIPELINE_REFERENCE_SEPARATOR = "@"
"""How a *Pipeline* is written on the command line — `name@version`, the same
spelling a *Model* has in routing keys and queue names."""


def registered_pipelines() -> list[Pipeline]:
    """Every *Pipeline* this *Orchestrator* publishes."""
    return [
        PageFromStaffPipelineV1("mzk-page", "1", layout_model=DVORAK_OLA, staff_model=AYCE_LONG),
        PageFromStaffPipelineV2("mzk-page", "2", layout_model=DVORAK_OLA, staff_model=AYCE_LONG),
        MzkStaffPipeline("mzk-staff", "1", staff_model=AYCE_LONG),
    ]


class PmcgSettings(OrchestratorHeadSettings):
    """What this *Orchestrator* is configured with, beyond the shared blocks.

    Only which of its *Pipelines* to announce. How any of them behaves is not
    configurable, by design — see the module docstring.
    """

    only_pipelines: list[str] = Field(
        default_factory=list,
        description="Announce only these pipelines, each written name@version. For development.",
    )
    """Announce only these *Pipelines*, each written `name@version`, rather
    than all of them. For development: a *Pipeline* being written is registered
    in `registered_pipelines` under a `-dev` version and started alone, so that
    a process running unfinished code takes no work meant for the *Pipelines*
    that are already published. Empty means every *Pipeline*."""


def selected_pipelines(pipelines: list[Pipeline], only: Sequence[str]) -> list[Pipeline]:
    """The `pipelines` named in `only`, or all of them when it is empty.

    A name that matches nothing stops the process at startup, rather than
    starting an *Orchestrator* that announces less than was asked of it.
    """
    if not only:
        return pipelines

    by_reference = {_spell(pipeline): pipeline for pipeline in pipelines}
    unknown = [reference for reference in only if reference not in by_reference]
    if unknown:
        raise ValueError(
            f"No pipeline is registered as {', '.join(unknown)}; "
            f"the registered ones are {', '.join(by_reference)}"
        )

    return [by_reference[reference] for reference in dict.fromkeys(only)]


def main() -> None:
    """Run the PMCG orchestrator until it is stopped."""
    settings = PmcgSettings.load()

    pipelines = selected_pipelines(registered_pipelines(), settings.only_pipelines)

    orchestrator = Orchestrator(ORCHESTRATOR_NAME, settings)
    for pipeline in pipelines:
        orchestrator.register_pipeline(pipeline)
    orchestrator.run()


def _spell(pipeline: Pipeline) -> str:
    return f"{pipeline.name}{PIPELINE_REFERENCE_SEPARATOR}{pipeline.version}"
