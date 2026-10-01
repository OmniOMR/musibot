"""`PageFromStaffPipelineV1`, end to end against two fake *Models*."""

from xml.etree import ElementTree

from pmcg_orchestrator.page_from_staff import PageFromStaffPipelineV1
from tests.fakes import LAYOUT_MODEL, STAFF_MODEL, a_runner, fails_staff

# Two staves, one above the other, in the 400x300 page the fakes make.
TWO_STAVES = ((20, 40, 360, 40), (20, 160, 360, 40))
# And a system box around each, which version 1 does not read.
TWO_SYSTEMS = ((10, 30, 380, 60), (10, 150, 380, 60))


def a_pipeline(name: str = "mzk-page", version: str = "1") -> PageFromStaffPipelineV1:
    return PageFromStaffPipelineV1(
        name, version, layout_model=LAYOUT_MODEL, staff_model=STAFF_MODEL
    )


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


def test_systems_in_the_layout_change_nothing() -> None:
    """Version 1 reads the staves alone, so a layout that also reports systems
    comes out exactly as one that does not."""
    without = a_runner(*TWO_STAVES)
    without.run(a_pipeline(), input=["image.jpg"])

    with_systems = a_runner(*TWO_STAVES, systems=TWO_SYSTEMS)
    with_systems.run(a_pipeline(), input=["image.jpg"])

    assert with_systems.files["transcription.musicxml"] == without.files["transcription.musicxml"]


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
