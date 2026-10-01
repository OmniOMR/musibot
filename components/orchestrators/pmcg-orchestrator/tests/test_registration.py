"""What this *Orchestrator* publishes, and how a development run narrows it."""

import pytest
from musibot.orchestrator_head import NameAndVersion

from pmcg_orchestrator import PmcgSettings, registered_pipelines, selected_pipelines
from pmcg_orchestrator.page_from_staff import PageFromStaffPipeline


def spelled() -> list[str]:
    return [f"{pipeline.name}@{pipeline.version}" for pipeline in registered_pipelines()]


def test_it_publishes_the_pipelines_the_web_ui_offers() -> None:
    # `components/web-ui/src/pipelines.ts` names these two outright, so a
    # registration that drifts away from them leaves the landing page with
    # nothing to recommend.
    assert "mzk-page@1" in spelled()
    assert "mzk-staff@1" in spelled()


def test_an_older_version_is_published_beside_the_newer_one() -> None:
    # Someone may still be pinning it.
    assert "mzk-page@1" in spelled()
    assert "mzk-page@2" in spelled()


def test_it_publishes_the_steps_of_mzk_page_one_by_one() -> None:
    # For running them by hand, with a human correcting what lies in between.
    assert {"pmcg-slice@1", "pmcg-glue@1", "pmcg-glue@2"} <= set(spelled())


def test_no_two_registrations_publish_the_same_pipeline() -> None:
    assert len(spelled()) == len(set(spelled()))


def test_every_version_of_mzk_page_runs_the_same_models() -> None:
    pages = [p for p in registered_pipelines() if isinstance(p, PageFromStaffPipeline)]

    assert [page.version for page in pages] == ["1", "2"]
    for page in pages:
        assert page._layout_model == NameAndVersion(name="dvorak-ola", version="2.0-2025-03-09")
        assert page._staff_model == NameAndVersion(
            name="ayce-long", version="2026-08-03-192253-final"
        )


def test_every_pipeline_is_announced_by_default() -> None:
    pipelines = registered_pipelines()

    assert selected_pipelines(pipelines, []) == pipelines


def test_a_development_run_announces_only_what_it_names() -> None:
    pipelines = registered_pipelines()

    [selected] = selected_pipelines(pipelines, ["mzk-staff@1"])

    assert (selected.name, selected.version) == ("mzk-staff", "1")


def test_naming_a_pipeline_twice_announces_it_once() -> None:
    assert len(selected_pipelines(registered_pipelines(), ["mzk-staff@1", "mzk-staff@1"])) == 1


@pytest.mark.parametrize("reference", ["mzk-page@99", "mzk-page", "mzk-page@2-dev", "nothing@1"])
def test_naming_an_unregistered_pipeline_stops_the_process(reference: str) -> None:
    # Rather than starting an Orchestrator that announces less than was asked.
    with pytest.raises(ValueError, match="No pipeline is registered as"):
        selected_pipelines(registered_pipelines(), [reference])


def test_the_selection_is_a_command_line_argument() -> None:
    settings = PmcgSettings.load(
        ["--only-pipelines", "mzk-page@1", "--only-pipelines", "x@2"], env={}
    )

    assert settings.only_pipelines == ["mzk-page@1", "x@2"]


def test_the_selection_is_an_environment_variable(monkeypatch: pytest.MonkeyPatch) -> None:
    # A list is written as JSON in the environment, as pydantic-settings reads it.
    monkeypatch.setenv("MUSIBOT_ONLY_PIPELINES", '["mzk-page@1"]')

    settings = PmcgSettings.load([], env={})

    assert settings.only_pipelines == ["mzk-page@1"]


def test_nothing_about_how_a_pipeline_behaves_is_configurable() -> None:
    # The settings a published Pipeline used to take from configuration. Each
    # would let a deployment change what a pinned name and version does.
    for removed in ("layout_model", "staff_model", "page_pipeline_version", "staff_padding_ratio"):
        assert removed not in PmcgSettings.model_fields
