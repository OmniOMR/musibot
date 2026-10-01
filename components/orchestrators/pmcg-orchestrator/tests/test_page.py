"""The `mzk-page` pipeline, end to end against two fake *Models*."""

import json
from xml.etree import ElementTree

import pytest
from musibot.orchestrator_head import ModelExecutionFailed
from musibot.orchestrator_head.testing import ModelCall, PipelineRunner

from pmcg_orchestrator.page import MzkPagePipeline
from tests.fakes import (
    LAYOUT_MODEL,
    STAFF_MODEL,
    a_page,
    a_runner,
    a_staff_transcription,
    fails_staff,
)

# Two staves, one above the other, in the 400x300 page the fakes make.
TWO_STAVES = ((20, 40, 360, 40), (20, 160, 360, 40))
# And a system box around each of them, making them one instrument's two lines.
TWO_SYSTEMS = ((10, 30, 380, 60), (10, 150, 380, 60))


def a_pipeline(name: str = "mzk-page", version: str = "1") -> MzkPagePipeline:
    return MzkPagePipeline(name, version, layout_model=LAYOUT_MODEL, staff_model=STAFF_MODEL)


# --- the whole thing ---------------------------------------------------------


def test_it_reads_a_page_into_a_page_level_transcription() -> None:
    runner = a_runner(*TWO_STAVES)

    runner.run(a_pipeline(), input=["image.jpg"])

    score = ElementTree.fromstring(runner.files["transcription.musicxml"])
    # With no system boxes in the layout, the page is one system spanning both
    # staves, so each staff is an instrument of its own, sounding at once.
    assert [part.get("id") for part in score.findall("part")] == ["P1", "P2"]
    for part in score.findall("part"):
        measures = part.findall("measure")
        assert [measure.get("number") for measure in measures] == ["1"]
        assert measures[0].find("print[@new-system='yes']") is None


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

    # Each step, in order. The gluing says a good deal more in between, which
    # is diagnostic detail rather than the steps a User follows.
    steps = [
        "Detecting grandstaff,staff,system with dvorak-ola 2.0-2025-03-09 ...",
        "Found 2 staves.",
        "Slicing the page into 2 staff images ...",
        "Transcribing 2 staves with ayce-long 2026-08-03-192253-final ...",
        "Writing transcription.musicxml ...",
        "Done.",
    ]
    assert [message for message in runner.log_messages() if message in steps] == steps


# --- the staves it finds -----------------------------------------------------


def test_staves_are_numbered_down_the_page() -> None:
    """The layout model orders its own output, but nothing says it must.

    So the pipeline sorts, and `Staves/1` has to be the topmost staff whatever
    order the document listed them in.
    """
    lower = (100, 200, 100, 20)  # + an 18px margin → 136x56
    upper = (100, 100, 200, 30)  # + a 27px margin → 254x84
    runner = a_runner(lower, upper)  # listed bottom first, on purpose

    runner.run(a_pipeline(), input=["image.jpg"])

    assert json.loads(runner.files["layout.json"])["annotations"][0]["bbox"] == list(lower)

    # The fake staff model writes each crop's size into its transcription, so
    # the sizes say which box became which staff.
    assert "254x84" in runner.files["Staves/1/transcription.musicxml"].decode("utf-8")
    assert "136x56" in runner.files["Staves/2/transcription.musicxml"].decode("utf-8")


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
    """0.9 of a 20px staff is 18px on each side, so 136x56 out of a 100x20 box."""
    runner = a_runner((100, 100, 100, 20))

    runner.run(a_pipeline(), input=["image.jpg"])

    # The fake staff model writes the crop's size into its transcription.
    transcription = runner.files["Staves/1/transcription.musicxml"].decode("utf-8")
    assert "136x56" in transcription


def test_the_margin_is_clamped_to_the_page() -> None:
    # A staff touching the top edge cannot be given a margin above it.
    runner = a_runner((0, 0, 400, 40))

    runner.run(a_pipeline(), input=["image.jpg"])

    transcription = runner.files["Staves/1/transcription.musicxml"].decode("utf-8")
    assert "400x76" in transcription


# --- when a staff fails ------------------------------------------------------


def test_one_failed_staff_leaves_the_rest_of_the_page_intact() -> None:
    runner = a_runner(*TWO_STAVES, staff_model=fails_staff(1))

    runner.run(a_pipeline(), input=["image.jpg"])

    score = ElementTree.fromstring(runner.files["transcription.musicxml"])
    # The failed staff still takes up its part, and says why in the score.
    assert len(score.findall("part/measure")) == 2
    assert [words.text for words in score.findall(".//direction//words")] == [
        "Cannot transcribe staff 1"
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


def test_a_system_where_every_staff_failed_leaves_the_rest_of_the_page_intact() -> None:
    """One instrument over two systems, and the second system's only staff fails.

    Nothing in that system was transcribed to say how many measures it has,
    which must not take the rest of the page down with it.
    """
    runner = a_runner(*TWO_STAVES, systems=TWO_SYSTEMS, staff_model=fails_staff(2))

    runner.run(a_pipeline(), input=["image.jpg"])

    score = ElementTree.fromstring(runner.files["transcription.musicxml"])
    assert [part.get("id") for part in score.findall("part")] == ["P1"]
    measures = score.findall("part/measure")
    assert [measure.get("number") for measure in measures] == ["1", "2"]
    assert measures[1].find("print[@new-system='yes']") is not None
    assert [words.text for words in score.findall(".//direction//words")] == [
        "Cannot transcribe staff 2"
    ]


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


# --- the score it writes ----------------------------------------------------


def test_a_padding_measure_is_valid_musicxml() -> None:
    """Two instruments in one system, the second transcribed one measure short.

    It is padded up to the first, and the padding's rest needs a duration like
    any other note: MusicXML requires one, and a reader that trusts it would
    otherwise reject the file.
    """

    def staff_2_is_shorter(call: ModelCall, files: dict[str, bytes]) -> None:
        [staff_image] = call.input
        folder = staff_image.rsplit("/", 1)[0]
        measures = 1 if folder == "Staves/2" else 2
        files[f"{folder}/transcription.musicxml"] = a_staff_transcription(measures=measures).encode(
            "utf-8"
        )

    runner = a_runner(*TWO_STAVES, staff_model=staff_2_is_shorter)

    runner.run(a_pipeline(), input=["image.jpg"])

    score = ElementTree.fromstring(runner.files["transcription.musicxml"])
    assert [len(part.findall("measure")) for part in score.findall("part")] == [2, 2]
    assert [words.text for words in score.findall(".//direction//words")] == ["Padding measure"]
    for note in score.iter("note"):
        assert note.findtext("duration") is not None


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
    development = a_pipeline(name="mzk-page", version="3-dev")

    assert (development.name, development.version) == ("mzk-page", "3-dev")
