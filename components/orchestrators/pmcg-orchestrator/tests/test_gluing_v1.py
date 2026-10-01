"""Gluing, version 1: every staff into one part, one after another."""

from xml.etree import ElementTree

import pytest

from pmcg_orchestrator.errors import UnreadableTranscription
from pmcg_orchestrator.gluing import StaffTranscription
from pmcg_orchestrator.gluing.v1 import glue
from tests.fakes import a_staff_transcription

# --- concatenating -----------------------------------------------------------


def test_every_staff_lands_in_the_one_part_in_order() -> None:
    document = glue(
        [
            StaffTranscription(number=1, musicxml=a_staff_transcription("first")),
            StaffTranscription(number=2, musicxml=a_staff_transcription("second")),
        ]
    )

    score = ElementTree.fromstring(document)
    # One part, whatever the page has staves: a page is usually one instrument's
    # music, and a part per staff reads it as that many playing at once.
    assert [part.get("id") for part in score.findall("part")] == ["P1"]
    assert [text.text for text in score.findall(".//lyric/text")] == ["first", "second"]


def test_measures_are_renumbered_across_the_whole_page() -> None:
    # Every staff transcription counts from 1, so keeping their numbers would
    # number the page 1, 2, 1, 2, 3 — and a measure number is what a person
    # quotes when they say where the recognition went wrong.
    document = glue(
        [
            StaffTranscription(number=1, musicxml=a_staff_transcription(measures=2)),
            StaffTranscription(number=2, musicxml=a_staff_transcription(measures=3)),
        ]
    )

    score = ElementTree.fromstring(document)
    assert [measure.get("number") for measure in score.findall("part/measure")] == [
        "1",
        "2",
        "3",
        "4",
        "5",
    ]


def test_each_staff_after_the_first_begins_a_new_system() -> None:
    """Which is what keeps the page looking like the page it came from."""
    document = glue(
        [
            StaffTranscription(number=1, musicxml=a_staff_transcription(measures=2)),
            StaffTranscription(number=2, musicxml=a_staff_transcription(measures=2)),
            StaffTranscription(number=3, musicxml=a_staff_transcription(measures=1)),
        ]
    )

    score = ElementTree.fromstring(document)
    breaks = [
        measure.get("number")
        for measure in score.findall("part/measure")
        if measure.find("print[@new-system='yes']") is not None
    ]
    # The third and the fifth measure open a system; the first does not, being
    # the beginning of the page rather than a break in it.
    assert breaks == ["3", "5"]


def test_the_break_is_the_first_thing_in_its_measure() -> None:
    # MusicXML puts `<print>` before the music it applies to.
    document = glue(
        [
            StaffTranscription(number=1, musicxml=a_staff_transcription()),
            StaffTranscription(number=2, musicxml=a_staff_transcription()),
        ]
    )

    score = ElementTree.fromstring(document)
    second = score.findall("part/measure")[1]
    assert second[0].tag == "print"


def test_staves_of_different_lengths_simply_follow_one_another() -> None:
    """The reason for one part rather than one per staff.

    Staff transcriptions of a real page never agree about how many measures
    there are, and parts that play at once have to.
    """
    document = glue(
        [
            StaffTranscription(number=1, musicxml=a_staff_transcription(measures=4)),
            StaffTranscription(number=2, musicxml=a_staff_transcription(measures=1)),
            StaffTranscription(number=3, musicxml=a_staff_transcription(measures=7)),
        ]
    )

    assert len(ElementTree.fromstring(document).findall("part/measure")) == 12


def test_the_part_list_comes_before_the_part() -> None:
    # MusicXML says so, and a reader that trusts the order would otherwise
    # reject the file.
    document = glue([StaffTranscription(number=1, musicxml=a_staff_transcription())])

    score = ElementTree.fromstring(document)
    assert [child.tag for child in score] == ["part-list", "part"]


def test_the_one_part_is_not_labelled_in_the_score() -> None:
    # A single-instrument score has no use for an instrument name down the left
    # margin, and this one would be made up.
    document = glue([StaffTranscription(number=1, musicxml=a_staff_transcription())])

    [name] = ElementTree.fromstring(document).findall(".//score-part/part-name")
    assert name.get("print-object") == "no"


def test_a_staff_that_was_not_transcribed_says_so_in_the_score() -> None:
    """An empty measure is otherwise indistinguishable from a staff the model
    read as silence, which is a worse thing to tell a User."""
    document = glue(
        [
            StaffTranscription(number=1, musicxml=a_staff_transcription()),
            StaffTranscription(number=2, error="the model could not read it"),
            StaffTranscription(number=3, musicxml=a_staff_transcription()),
        ]
    )

    score = ElementTree.fromstring(document)
    # It still takes up a system, so the page does not silently close the gap.
    assert len(score.findall("part/measure")) == 3
    assert [words.text for words in score.findall(".//direction//words")] == [
        "Staff 2 could not be transcribed"
    ]


def test_a_placeholder_in_the_middle_does_not_rewrite_the_page_s_durations() -> None:
    """`divisions` carries forward from measure to measure.

    Restating it in a placeholder would silently rescale every duration after
    it, which is a worse failure than the missing staff it stands for.
    """
    document = glue(
        [
            StaffTranscription(number=1, musicxml=a_staff_transcription()),
            StaffTranscription(number=2, error="no"),
        ]
    )

    score = ElementTree.fromstring(document)
    placeholder = score.findall("part/measure")[1]
    assert placeholder.find("attributes") is None


def test_a_page_that_opens_with_a_placeholder_still_has_a_scale() -> None:
    # Nothing has said what a division is yet, so this one has to.
    document = glue(
        [
            StaffTranscription(number=1, error="no"),
            StaffTranscription(number=2, musicxml=a_staff_transcription()),
        ]
    )

    score = ElementTree.fromstring(document)
    first = score.findall("part/measure")[0]
    assert first.findtext("attributes/divisions") == "1"


def test_a_transcription_that_is_not_xml_is_refused() -> None:
    with pytest.raises(UnreadableTranscription, match="not valid XML"):
        glue([StaffTranscription(number=1, musicxml="<score-partwise")])


def test_a_transcription_with_no_measures_is_refused() -> None:
    with pytest.raises(UnreadableTranscription, match="contains no measures"):
        glue([StaffTranscription(number=1, musicxml="<score-partwise/>")])


def test_the_document_declares_its_encoding() -> None:
    document = glue([StaffTranscription(number=1, musicxml=a_staff_transcription())])

    assert document.startswith('<?xml version="1.0" encoding="UTF-8"?>')
