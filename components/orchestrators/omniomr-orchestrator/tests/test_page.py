"""The `mzk-page` pipeline, end to end against two fake *Models*."""

import json
from xml.etree import ElementTree

import pytest
from musibot.orchestrator_head import ModelExecutionFailed
from musibot.orchestrator_head.testing import PipelineRunner

from omniomr_orchestrator.page import MzkPagePipeline
from tests.fakes import LAYOUT_MODEL, STAFF_MODEL, a_page, a_runner, fails_staff

# Two staves, one above the other, in the 400x300 page the fakes make.
TWO_STAVES = ((20, 40, 360, 40), (20, 160, 360, 40))


def a_pipeline(name: str = "mzk-page", version: str = "1", **overrides: object) -> MzkPagePipeline:
    parameters: dict[str, object] = {
        "layout_model": LAYOUT_MODEL,
        "staff_model": STAFF_MODEL,
        **overrides,
    }
    return MzkPagePipeline(name, version, **parameters)  # type: ignore[arg-type]


# --- the whole thing ---------------------------------------------------------


def test_it_reads_a_page_into_a_page_level_transcription() -> None:
    runner = a_runner(*TWO_STAVES)

    runner.run(a_pipeline(), input=["image.jpg"])

    score = ElementTree.fromstring(runner.files["transcription.musicxml"])
    # One part holding both staves, one after the other, with a system break
    # where the second begins.
    assert [part.get("id") for part in score.findall("part")] == ["P1"]
    measures = score.findall("part/measure")
    assert [measure.get("number") for measure in measures] == ["1", "2"]
    assert measures[1].find("print[@new-system='yes']") is not None


def test_it_runs_the_models_it_was_pinned_to_in_order() -> None:
    runner = a_runner(*TWO_STAVES)

    runner.run(a_pipeline(), input=["image.jpg"])

    assert [(call.model, call.input) for call in runner.model_calls] == [
        (LAYOUT_MODEL, ["image.jpg"]),
        (STAFF_MODEL, ["Staves/1/image.jpg"]),
        (STAFF_MODEL, ["Staves/2/image.jpg"]),
    ]


def test_it_leaves_the_intermediate_files_in_the_page() -> None:
    # They are what somebody looks at when the result is wrong.
    runner = a_runner(*TWO_STAVES)

    runner.run(a_pipeline(), input=["image.jpg"])

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


def test_it_narrates_each_step() -> None:
    runner = a_runner(*TWO_STAVES)

    runner.run(a_pipeline(), input=["image.jpg"])

    assert runner.log_messages() == [
        "Detecting staves with dvorak-ola 2.0-2025-03-09 ...",
        "Found 2 staves.",
        "Slicing the page into 2 staff images ...",
        "Transcribing 2 staves with ayce-long 2026-08-03-192253-final ...",
        "Writing transcription.musicxml ...",
        "Done.",
    ]


# --- the staves it finds -----------------------------------------------------


def test_staves_are_numbered_down_the_page() -> None:
    """The layout model orders its own output, but nothing says it must.

    So the pipeline sorts, and `Staves/1` has to be the topmost staff whatever
    order the document listed them in.
    """
    lower = (20, 200, 360, 40)  # + a 10px margin → 380x60
    upper = (20, 40, 300, 60)  # + a 15px margin → 330x90
    runner = a_runner(lower, upper)  # listed bottom first, on purpose

    runner.run(a_pipeline(staff_padding_ratio=0.25), input=["image.jpg"])

    assert json.loads(runner.files["layout.json"])["annotations"][0]["bbox"] == list(lower)

    # The fake staff model writes each crop's size into its transcription, so
    # the sizes say which box became which staff.
    assert "330x90" in runner.files["Staves/1/transcription.musicxml"].decode("utf-8")
    assert "380x60" in runner.files["Staves/2/transcription.musicxml"].decode("utf-8")


def test_a_page_with_no_staves_says_so_rather_than_writing_an_empty_score() -> None:
    runner = a_runner()  # a cover, a title page, a blank

    with pytest.raises(ValueError, match="No staves were found"):
        runner.run(a_pipeline(), input=["image.jpg"])

    assert "transcription.musicxml" not in runner.files


def test_a_layout_that_is_not_json_is_reported_legibly() -> None:
    def writes_nonsense(call: object, files: dict[str, bytes]) -> None:
        files["layout.json"] = b"not json at all"

    runner = PipelineRunner({"image.jpg": a_page()})
    runner.register_model(LAYOUT_MODEL, writes_nonsense)
    runner.register_model(STAFF_MODEL)

    with pytest.raises(ValueError, match="is not JSON"):
        runner.run(a_pipeline(), input=["image.jpg"])


# --- the crops ---------------------------------------------------------------


def test_a_staff_crop_carries_a_margin_of_its_own_height() -> None:
    """0.25 of a 40px staff is 10px on each side, so 380x60 out of a 360x40 box."""
    runner = a_runner((20, 40, 360, 40))

    runner.run(a_pipeline(staff_padding_ratio=0.25), input=["image.jpg"])

    # The fake staff model writes the crop's size into its transcription.
    transcription = runner.files["Staves/1/transcription.musicxml"].decode("utf-8")
    assert "380x60" in transcription


def test_the_margin_is_clamped_to_the_page() -> None:
    # A staff touching the top edge cannot be given a margin above it.
    runner = a_runner((0, 0, 400, 40))

    runner.run(a_pipeline(staff_padding_ratio=0.25), input=["image.jpg"])

    transcription = runner.files["Staves/1/transcription.musicxml"].decode("utf-8")
    assert "400x50" in transcription


def test_no_margin_is_the_bare_box() -> None:
    runner = a_runner((20, 40, 360, 40))

    runner.run(a_pipeline(staff_padding_ratio=0.0), input=["image.jpg"])

    transcription = runner.files["Staves/1/transcription.musicxml"].decode("utf-8")
    assert "360x40" in transcription


# --- when a staff fails ------------------------------------------------------


def test_one_failed_staff_leaves_the_rest_of_the_page_intact() -> None:
    runner = a_runner(*TWO_STAVES, staff_model=fails_staff(1))

    runner.run(a_pipeline(), input=["image.jpg"])

    score = ElementTree.fromstring(runner.files["transcription.musicxml"])
    # The failed staff still takes up a system, and says why in the score.
    assert len(score.findall("part/measure")) == 2
    assert [words.text for words in score.findall(".//direction//words")] == [
        "Staff 1 could not be transcribed"
    ]


def test_a_failed_staff_is_named_in_the_log() -> None:
    runner = a_runner(*TWO_STAVES, staff_model=fails_staff(2, "Nothing legible here."))

    runner.run(a_pipeline(), input=["image.jpg"])

    errors = [line.message for line in runner.logs if line.level == "error"]
    assert len(errors) == 1
    assert "Staff 2" in errors[0]
    assert "Nothing legible here." in errors[0]

    warnings = [line.message for line in runner.logs if line.level == "warning"]
    assert warnings == ["Transcribed 1 of 2 staves."]


def test_a_page_where_every_staff_failed_is_a_failure() -> None:
    def fails_everything(call: object, files: dict[str, bytes]) -> None:
        raise RuntimeError("The model is having a bad day.")

    runner = a_runner(*TWO_STAVES)
    runner.register_model(STAFF_MODEL, fails_everything)

    with pytest.raises(ModelExecutionFailed, match="none of the 2 staves"):
        runner.run(a_pipeline(), input=["image.jpg"])

    assert "transcription.musicxml" not in runner.files


def test_a_model_that_reports_success_and_writes_nothing_fails_its_staff() -> None:
    # Indistinguishable from a failure, from this pipeline's side, and it must
    # not become a part claiming to be a transcription.
    runner = a_runner(*TWO_STAVES, staff_model=lambda call, files: None)

    with pytest.raises(ModelExecutionFailed):
        runner.run(a_pipeline(), input=["image.jpg"])


# --- the declaration ---------------------------------------------------------


def test_it_declares_everything_the_execution_leaves_behind() -> None:
    signature = a_pipeline().description().signature

    assert signature.input == ["image.jpg"]
    assert signature.output == [
        "layout.json",
        "Staves/{*s}/image.jpg",
        "Staves/{*s}/transcription.musicxml",
        "Staves/{*s}/transcription.lmx?",
        "transcription.musicxml",
    ]


def test_the_name_and_version_are_the_registration_s_to_choose() -> None:
    development = a_pipeline(name="mzk-dev", version="2")

    assert (development.name, development.version) == ("mzk-dev", "2")
