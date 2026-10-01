"""What every version of `PageFromStaffPipeline` does alike, run against each."""

import json

import pytest
from musibot.orchestrator_head import ModelExecutionFailed
from musibot.orchestrator_head.testing import PipelineRunner

from pmcg_orchestrator.page_from_staff import (
    PageFromStaffPipeline,
    PageFromStaffPipelineV1,
    PageFromStaffPipelineV2,
)
from tests.fakes import LAYOUT_MODEL, STAFF_MODEL, a_page, a_runner, fails_staff

# Two staves, one above the other, in the 400x300 page the fakes make.
TWO_STAVES = ((20, 40, 360, 40), (20, 160, 360, 40))


@pytest.fixture(params=[PageFromStaffPipelineV1, PageFromStaffPipelineV2], ids=["v1", "v2"])
def implementation(request: pytest.FixtureRequest) -> type[PageFromStaffPipeline]:
    cls: type[PageFromStaffPipeline] = request.param
    return cls


def a_pipeline(
    cls: type[PageFromStaffPipeline], name: str = "mzk-page", version: str = "1"
) -> PageFromStaffPipeline:
    return cls(name, version, layout_model=LAYOUT_MODEL, staff_model=STAFF_MODEL)


# --- the whole thing ---------------------------------------------------------


def test_it_runs_the_models_it_was_pinned_to_in_order(
    implementation: type[PageFromStaffPipeline],
) -> None:
    runner = a_runner(*TWO_STAVES)

    runner.run(a_pipeline(implementation), input=["image.jpg"])

    assert [(call.model, call.input) for call in runner.model_calls] == [
        (LAYOUT_MODEL, ["image.jpg"]),
        (STAFF_MODEL, ["Staves/1/image.jpg"]),
        (STAFF_MODEL, ["Staves/2/image.jpg"]),
    ]


def test_it_leaves_the_intermediate_files_in_the_page(
    implementation: type[PageFromStaffPipeline],
) -> None:
    # They are what somebody looks at when the result is wrong.
    runner = a_runner(*TWO_STAVES)

    runner.run(a_pipeline(implementation), input=["image.jpg"])

    assert set(runner.files) == {
        "image.jpg",
        "layout.json",
        "Staves/1/image.jpg",
        "Staves/2/image.jpg",
        "Staves/1/transcription.musicxml",
        "Staves/2/transcription.musicxml",
        "transcription.musicxml",
    }
    # Only what this pipeline wrote itself is announced by it; the staff
    # transcriptions are the Model's to announce.
    assert runner.written == [
        "Staves/1/image.jpg",
        "Staves/2/image.jpg",
        "transcription.musicxml",
    ]


# --- the staves it finds -----------------------------------------------------


def test_staves_are_numbered_down_the_page(implementation: type[PageFromStaffPipeline]) -> None:
    """The layout model orders its own output, but nothing says it must.

    So the pipeline sorts, and `Staves/1` has to be the topmost staff whatever
    order the document listed them in.
    """
    lower = (100, 200, 100, 20)  # + an 18px margin → 136x56
    upper = (100, 100, 200, 30)  # + a 27px margin → 254x84
    runner = a_runner(lower, upper)  # listed bottom first, on purpose

    runner.run(a_pipeline(implementation), input=["image.jpg"])

    assert json.loads(runner.files["layout.json"])["annotations"][0]["bbox"] == list(lower)

    # The fake staff model writes each crop's size into its transcription, so
    # the sizes say which box became which staff.
    assert "254x84" in runner.files["Staves/1/transcription.musicxml"].decode("utf-8")
    assert "136x56" in runner.files["Staves/2/transcription.musicxml"].decode("utf-8")


def test_a_page_with_no_staves_says_so_rather_than_writing_an_empty_score(
    implementation: type[PageFromStaffPipeline],
) -> None:
    runner = a_runner()  # a cover, a title page, a blank

    with pytest.raises(ValueError, match="No staves were found"):
        runner.run(a_pipeline(implementation), input=["image.jpg"])

    assert "transcription.musicxml" not in runner.files


def test_a_layout_that_is_not_json_is_reported_legibly(
    implementation: type[PageFromStaffPipeline],
) -> None:
    def writes_nonsense(call: object, files: dict[str, bytes]) -> None:
        files["layout.json"] = b"not json at all"

    runner = PipelineRunner({"image.jpg": a_page()})
    runner.register_model(LAYOUT_MODEL, writes_nonsense)
    runner.register_model(STAFF_MODEL)

    with pytest.raises(ValueError, match="is not JSON"):
        runner.run(a_pipeline(implementation), input=["image.jpg"])


# --- the crops ---------------------------------------------------------------


def test_a_staff_crop_carries_a_margin_of_its_own_height(
    implementation: type[PageFromStaffPipeline],
) -> None:
    """0.9 of a 20px staff is 18px on each side, so 136x56 out of a 100x20 box."""
    runner = a_runner((100, 100, 100, 20))

    runner.run(a_pipeline(implementation), input=["image.jpg"])

    # The fake staff model writes the crop's size into its transcription.
    transcription = runner.files["Staves/1/transcription.musicxml"].decode("utf-8")
    assert "136x56" in transcription


def test_the_margin_is_clamped_to_the_page(implementation: type[PageFromStaffPipeline]) -> None:
    # A staff touching the top edge cannot be given a margin above it.
    runner = a_runner((0, 0, 400, 40))

    runner.run(a_pipeline(implementation), input=["image.jpg"])

    transcription = runner.files["Staves/1/transcription.musicxml"].decode("utf-8")
    assert "400x76" in transcription


# --- when a staff fails ------------------------------------------------------


def test_a_failed_staff_is_named_in_the_log(implementation: type[PageFromStaffPipeline]) -> None:
    runner = a_runner(*TWO_STAVES, staff_model=fails_staff(2, "Nothing legible here."))

    runner.run(a_pipeline(implementation), input=["image.jpg"])

    errors = [line.message for line in runner.logs if line.level == "error"]
    assert len(errors) == 1
    assert "Staff 2" in errors[0]
    assert "Nothing legible here." in errors[0]

    warnings = [line.message for line in runner.logs if line.level == "warning"]
    assert warnings == ["Transcribed 1 of 2 staves."]


def test_a_page_where_every_staff_failed_is_a_failure(
    implementation: type[PageFromStaffPipeline],
) -> None:
    def fails_everything(call: object, files: dict[str, bytes]) -> None:
        raise RuntimeError("The model is having a bad day.")

    runner = a_runner(*TWO_STAVES)
    runner.register_model(STAFF_MODEL, fails_everything)

    with pytest.raises(ModelExecutionFailed, match="none of the 2 staves"):
        runner.run(a_pipeline(implementation), input=["image.jpg"])

    assert "transcription.musicxml" not in runner.files


def test_a_model_that_reports_success_and_writes_nothing_fails_its_staff(
    implementation: type[PageFromStaffPipeline],
) -> None:
    # Indistinguishable from a failure, from this pipeline's side, and it must
    # not become a part claiming to be a transcription.
    runner = a_runner(*TWO_STAVES, staff_model=lambda call, files: None)

    with pytest.raises(ModelExecutionFailed):
        runner.run(a_pipeline(implementation), input=["image.jpg"])


# --- the declaration ---------------------------------------------------------


def test_it_declares_everything_the_execution_leaves_behind(
    implementation: type[PageFromStaffPipeline],
) -> None:
    signature = a_pipeline(implementation).description().signature

    assert signature.input == ["image.jpg"]
    assert signature.output == [
        "layout.json",
        "Staves/{*s}/image.jpg",
        "Staves/{*s}/transcription.musicxml",
        "Staves/{*s}/transcription.lmx?",
        "transcription.musicxml",
    ]


def test_the_name_and_version_are_the_registration_s_to_choose(
    implementation: type[PageFromStaffPipeline],
) -> None:
    development = a_pipeline(implementation, name="mzk-page", version="3-dev")

    assert (development.name, development.version) == ("mzk-page", "3-dev")
