"""The `mzk-staff` pipeline: the transcription *Model*, under a stable name."""

import pytest
from musibot.orchestrator_head import ModelExecutionFailed
from musibot.orchestrator_head.testing import ModelCall, PipelineRunner

from omniomr_orchestrator.staff import MzkStaffPipeline
from tests.fakes import STAFF_MODEL, a_page, a_staff_transcription

STAFF_IMAGE = "Staves/1/image.jpg"
STAFF_TRANSCRIPTION = "Staves/1/transcription.musicxml"


def a_pipeline(name: str = "mzk-staff", version: str = "1") -> MzkStaffPipeline:
    return MzkStaffPipeline(name, version, staff_model=STAFF_MODEL)


def transcribes(call: ModelCall, files: dict[str, bytes]) -> None:
    """A staff model writing beside the *File* it was given, as they do."""
    folder = call.input[0].rsplit("/", 1)[0]
    files[f"{folder}/transcription.musicxml"] = a_staff_transcription().encode("utf-8")


def a_runner() -> PipelineRunner:
    runner = PipelineRunner({STAFF_IMAGE: a_page()})
    runner.register_model(STAFF_MODEL, transcribes)
    return runner


def test_it_hands_the_model_the_file_the_user_named() -> None:
    runner = a_runner()

    runner.run(a_pipeline(), input=[STAFF_IMAGE])

    assert [(call.model, call.input) for call in runner.model_calls] == [
        (STAFF_MODEL, [STAFF_IMAGE])
    ]
    assert STAFF_TRANSCRIPTION in runner.files


def test_it_forwards_whichever_staff_it_was_given() -> None:
    # The *User* chooses the instance name; nothing here assumes `Staves/1`.
    runner = PipelineRunner({"Staves/7/image.jpg": a_page()})
    runner.register_model(STAFF_MODEL, transcribes)

    runner.run(a_pipeline(), input=["Staves/7/image.jpg"])

    assert runner.model_calls[0].input == ["Staves/7/image.jpg"]
    assert "Staves/7/transcription.musicxml" in runner.files


def test_it_writes_nothing_of_its_own() -> None:
    """It runs a *Model* and stops. Everything in the page is the *Model's*."""
    runner = a_runner()

    runner.run(a_pipeline(), input=[STAFF_IMAGE])

    assert runner.written == []


def test_a_model_that_fails_fails_the_pipeline() -> None:
    def refuses(call: ModelCall, files: dict[str, bytes]) -> None:
        raise RuntimeError("Nothing legible on this staff.")

    runner = PipelineRunner({STAFF_IMAGE: a_page()})
    runner.register_model(STAFF_MODEL, refuses)

    with pytest.raises(ModelExecutionFailed, match="Nothing legible"):
        runner.run(a_pipeline(), input=[STAFF_IMAGE])


def test_it_declares_the_models_own_shape() -> None:
    """Which is what tells the *Web UI* to upload to `Staves/1/image.jpg`
    rather than to `image.jpg`, and what makes one staff one execution."""
    signature = a_pipeline().description().signature

    assert signature.input == ["Staves/{s}/image.jpg"]
    assert signature.output == [
        "Staves/{s}/transcription.musicxml",
        "Staves/{s}/transcription.lmx?",
    ]


def test_a_page_level_image_is_not_something_it_accepts() -> None:
    # The `api` service refuses this before it reaches an Orchestrator, and the
    # runner applies the same check — a whole page handed to a staff model
    # would be transcribed as one enormous staff and come back confident.
    runner = a_runner()

    with pytest.raises(Exception, match="image.jpg"):
        runner.run(a_pipeline(), input=["image.jpg"])
