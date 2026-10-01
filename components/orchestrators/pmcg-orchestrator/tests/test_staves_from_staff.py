"""`StavesFromStaffPipeline`: the transcription *Model*, under a stable name, over many staves."""

import pytest
from musibot.orchestrator_head import ModelExecutionFailed
from musibot.orchestrator_head.testing import ModelCall, PipelineRunner

from pmcg_orchestrator.staves_from_staff import StavesFromStaffPipeline
from tests.fakes import STAFF_MODEL, a_page, a_staff_transcription

STAFF_IMAGE = "Staves/1/image.jpg"
STAFF_TRANSCRIPTION = "Staves/1/transcription.musicxml"


def a_pipeline(name: str = "mzk-staff", version: str = "1") -> StavesFromStaffPipeline:
    return StavesFromStaffPipeline(name, version, staff_model=STAFF_MODEL)


def transcribes(call: ModelCall, files: dict[str, bytes]) -> None:
    """A staff model writing beside the *File* it was given, as they do."""
    folder = call.input[0].rsplit("/", 1)[0]
    files[f"{folder}/transcription.musicxml"] = a_staff_transcription().encode("utf-8")


def a_runner(*images: str, staff_model: object = transcribes) -> PipelineRunner:
    runner = PipelineRunner({image: a_page() for image in images or (STAFF_IMAGE,)})
    runner.register_model(STAFF_MODEL, staff_model)  # type: ignore[arg-type]
    return runner


def fails(*folders: str) -> object:
    """A staff model that fails the staves in these folders and transcribes the rest."""

    def behaviour(call: ModelCall, files: dict[str, bytes]) -> None:
        if call.input[0].rsplit("/", 1)[0] in folders:
            raise RuntimeError("Nothing legible on this staff.")
        transcribes(call, files)

    return behaviour


# --- one staff ---------------------------------------------------------------


def test_it_hands_the_model_the_file_the_user_named() -> None:
    runner = a_runner()

    runner.run(a_pipeline(), input=[STAFF_IMAGE])

    assert [(call.model, call.input) for call in runner.model_calls] == [
        (STAFF_MODEL, [STAFF_IMAGE])
    ]
    assert STAFF_TRANSCRIPTION in runner.files


def test_it_forwards_whichever_staff_it_was_given() -> None:
    # The *User* chooses the instance name; nothing here assumes `Staves/1`.
    runner = a_runner("Staves/7/image.jpg")

    runner.run(a_pipeline(), input=["Staves/7/image.jpg"])

    assert runner.model_calls[0].input == ["Staves/7/image.jpg"]
    assert "Staves/7/transcription.musicxml" in runner.files


def test_it_writes_nothing_of_its_own() -> None:
    """It runs a *Model* and stops. Everything in the page is the *Model's*."""
    runner = a_runner()

    runner.run(a_pipeline(), input=[STAFF_IMAGE])

    assert runner.written == []


def test_a_model_that_fails_its_only_staff_fails_the_pipeline_with_its_reason() -> None:
    runner = a_runner(staff_model=fails("Staves/1"))

    with pytest.raises(ModelExecutionFailed, match="Nothing legible"):
        runner.run(a_pipeline(), input=[STAFF_IMAGE])


def test_a_model_that_reports_success_and_writes_nothing_fails_its_staff() -> None:
    runner = a_runner(staff_model=lambda call, files: None)

    with pytest.raises(ModelExecutionFailed, match="wrote no Staves/1/transcription.musicxml"):
        runner.run(a_pipeline(), input=[STAFF_IMAGE])


# --- many staves -------------------------------------------------------------


def test_it_runs_the_model_once_per_staff() -> None:
    """One execution per staff, which is what makes one bad staff fail alone."""
    images = ["Staves/1/image.jpg", "Staves/2/image.jpg", "Staves/4/image.jpg"]
    runner = a_runner(*images)

    runner.run(a_pipeline(), input=images)

    assert sorted(call.input[0] for call in runner.model_calls) == images
    for folder in ("Staves/1", "Staves/2", "Staves/4"):
        assert f"{folder}/transcription.musicxml" in runner.files


def test_one_failed_staff_leaves_the_rest_transcribed() -> None:
    images = ["Staves/1/image.jpg", "Staves/2/image.jpg"]
    runner = a_runner(*images, staff_model=fails("Staves/1"))

    runner.run(a_pipeline(), input=images)

    assert "Staves/1/transcription.musicxml" not in runner.files
    assert "Staves/2/transcription.musicxml" in runner.files

    [error] = [line.message for line in runner.logs if line.level == "error"]
    assert error.startswith("Staves/1/image.jpg could not be transcribed: ")
    assert "Nothing legible on this staff." in error
    warnings = [line.message for line in runner.logs if line.level == "warning"]
    assert warnings == ["Transcribed 1 of 2 staves."]


def test_every_staff_failing_is_a_failure() -> None:
    images = ["Staves/1/image.jpg", "Staves/2/image.jpg"]
    runner = a_runner(*images, staff_model=fails("Staves/1", "Staves/2"))

    with pytest.raises(ModelExecutionFailed, match="none of the 2 staves"):
        runner.run(a_pipeline(), input=images)


def test_no_staves_at_all_is_refused() -> None:
    # `{*s}` matches an empty set, so the signature lets this through.
    runner = a_runner()

    with pytest.raises(ValueError, match="No staff images were given"):
        runner.run(a_pipeline(), input=[])


# --- the declaration ---------------------------------------------------------


def test_it_declares_the_models_shape_widened_to_a_set() -> None:
    """One staff is still a set of one, which is what the *Web UI* sends."""
    signature = a_pipeline().description().signature

    assert signature.input == ["Staves/{*s}/image.jpg"]
    assert signature.output == [
        "Staves/{*s}/transcription.musicxml",
        "Staves/{*s}/transcription.lmx?",
    ]


def test_a_page_level_image_is_not_something_it_accepts() -> None:
    # The `api` service refuses this before it reaches an Orchestrator, and the
    # runner applies the same check — a whole page handed to a staff model
    # would be transcribed as one enormous staff and come back confident.
    runner = a_runner()

    with pytest.raises(Exception, match="image.jpg"):
        runner.run(a_pipeline(), input=["image.jpg"])
