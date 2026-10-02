"""`PageFromStaffPipelineV2`, end to end against two fake *Models*."""

from xml.etree import ElementTree

from musibot.orchestrator_head.testing import ModelCall

from pmcg_orchestrator.page_from_staff import PageFromStaffPipelineV2
from tests.fakes import (
    LAYOUT_MODEL,
    STAFF_MODEL,
    a_runner,
    a_staff_transcription,
    fails_staff,
)

# Two staves, one above the other, in the 400x300 page the fakes make.
TWO_STAVES = ((20, 40, 360, 40), (20, 160, 360, 40))
# And a system box around each of them, making them one instrument's two lines.
TWO_SYSTEMS = ((10, 30, 380, 60), (10, 150, 380, 60))


def a_pipeline(name: str = "mzk-page", version: str = "2") -> PageFromStaffPipelineV2:
    return PageFromStaffPipelineV2(
        name, version, layout_model=LAYOUT_MODEL, staff_model=STAFF_MODEL
    )


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


# --- the score it writes -----------------------------------------------------


def test_a_padding_measure_is_a_hidden_measure_rest() -> None:
    """Two instruments in one system, the second transcribed one measure short.

    It is padded up to the first with a hidden full-measure rest that carries
    no `<duration>` — deliberately, though MusicXML asks for one. Setting it
    would mean knowing the current divisions and time signature, and a guessed
    duration of 1 makes MuseScore render a mess, while a rest without one is
    rendered as the full-measure rest it is meant to be. See the HACK note in
    `gluing.v2._placeholder_measure`.
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

    padding = score.findall("part")[1].findall("measure")[1]
    [note] = padding.findall("note")
    assert note.get("print-object") == "no"
    assert note.find("rest[@measure='yes']") is not None
    assert note.find("duration") is None
    # Nor does it restate `divisions`, which would rescale what follows.
    assert padding.find("attributes/divisions") is None
