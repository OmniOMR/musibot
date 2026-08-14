"""The parts of `mzk` that are not the pipeline: layout, slicing, concatenation.

These are the pieces that will move into a Musicorpus library when there is one,
so they are tested as the plain functions they are.
"""

import json
from xml.etree import ElementTree

import pytest

from omniomr_orchestrator import OmniOmrSettings, model_reference
from omniomr_orchestrator.layout import StaffBox, UnreadableLayout, staff_boxes
from omniomr_orchestrator.musicxml import (
    StaffTranscription,
    UnreadableTranscription,
    page_musicxml,
)
from omniomr_orchestrator.slicing import UnreadableImage, crop_staff, decode_page, slice_page
from tests.fakes import a_layout, a_page, a_staff_transcription

# --- reading the layout ------------------------------------------------------


def test_it_reads_the_staff_boxes_in_reading_order() -> None:
    layout = json.loads(a_layout((10, 200, 100, 20), (10, 50, 100, 20), (200, 50, 100, 20)))

    assert staff_boxes(layout) == [
        StaffBox(10, 50, 100, 20),
        StaffBox(200, 50, 100, 20),
        StaffBox(10, 200, 100, 20),
    ]


def test_the_staff_category_id_is_read_from_the_document() -> None:
    """Not hard-coded to 0: a document says which id it used, and reading that
    is the difference between working with any producer and one."""
    layout = {
        "categories": [{"id": 7, "name": "staff"}, {"id": 0, "name": "system"}],
        "annotations": [
            {"category_id": 7, "bbox": [10, 10, 100, 20]},
            {"category_id": 0, "bbox": [0, 0, 400, 300]},
        ],
    }

    assert staff_boxes(layout) == [StaffBox(10, 10, 100, 20)]


def test_a_layout_with_no_staff_category_has_no_staves() -> None:
    # The model lists only the categories a page actually has, so a page with
    # no staves on it simply does not mention them.
    assert staff_boxes(json.loads(a_layout(categories=False))) == []


def test_a_bbox_that_is_not_four_numbers_is_refused() -> None:
    layout = {
        "categories": [{"id": 0, "name": "staff"}],
        "annotations": [{"category_id": 0, "bbox": [10, 10, 100]}],
    }

    with pytest.raises(UnreadableLayout, match="not \\[x, y, width, height\\]"):
        staff_boxes(layout)


def test_a_float_bbox_is_rounded_rather_than_refused() -> None:
    layout = {
        "categories": [{"id": 0, "name": "staff"}],
        "annotations": [{"category_id": 0, "bbox": [10.4, 10.6, 100.0, 20.0]}],
    }

    assert staff_boxes(layout) == [StaffBox(10, 11, 100, 20)]


# --- slicing -----------------------------------------------------------------


def test_a_crop_is_the_box_plus_a_share_of_its_own_height() -> None:
    page = decode_page(a_page(400, 300))

    crop = crop_staff(page, StaffBox(100, 100, 200, 40), padding_ratio=0.25)

    assert crop.shape[:2] == (60, 220)  # 40 + 2*10 tall, 200 + 2*10 wide


def test_a_crop_at_the_edge_is_clamped_to_the_page() -> None:
    page = decode_page(a_page(400, 300))

    crop = crop_staff(page, StaffBox(0, 0, 400, 40), padding_ratio=0.5)

    assert crop.shape[:2] == (60, 400)  # 20px below, nothing above or beside


def test_a_box_outside_the_page_is_refused_legibly() -> None:
    page = decode_page(a_page(400, 300))

    with pytest.raises(UnreadableImage, match="does not overlap"):
        crop_staff(page, StaffBox(500, 500, 100, 20), padding_ratio=0.0)


def test_something_that_is_not_an_image_is_refused_legibly() -> None:
    with pytest.raises(UnreadableImage, match="could not be decoded"):
        decode_page(b"this is not a JPEG")


def test_slicing_a_page_returns_one_jpeg_per_box() -> None:
    crops = slice_page(a_page(), [StaffBox(10, 10, 100, 20), StaffBox(10, 50, 100, 20)], 0.0)

    assert len(crops) == 2
    assert all(crop.startswith(b"\xff\xd8") for crop in crops)  # JPEG's magic


# --- concatenating -----------------------------------------------------------


def test_every_staff_lands_in_the_one_part_in_order() -> None:
    document = page_musicxml(
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
    document = page_musicxml(
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
    document = page_musicxml(
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
    document = page_musicxml(
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
    document = page_musicxml(
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
    document = page_musicxml([StaffTranscription(number=1, musicxml=a_staff_transcription())])

    score = ElementTree.fromstring(document)
    assert [child.tag for child in score] == ["part-list", "part"]


def test_the_one_part_is_not_labelled_in_the_score() -> None:
    # A single-instrument score has no use for an instrument name down the left
    # margin, and this one would be made up.
    document = page_musicxml([StaffTranscription(number=1, musicxml=a_staff_transcription())])

    [name] = ElementTree.fromstring(document).findall(".//score-part/part-name")
    assert name.get("print-object") == "no"


def test_a_staff_that_was_not_transcribed_says_so_in_the_score() -> None:
    """An empty measure is otherwise indistinguishable from a staff the model
    read as silence, which is a worse thing to tell a User."""
    document = page_musicxml(
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
    document = page_musicxml(
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
    document = page_musicxml(
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
        page_musicxml([StaffTranscription(number=1, musicxml="<score-partwise")])


def test_a_transcription_with_no_measures_is_refused() -> None:
    with pytest.raises(UnreadableTranscription, match="contains no measures"):
        page_musicxml([StaffTranscription(number=1, musicxml="<score-partwise/>")])


def test_the_document_declares_its_encoding() -> None:
    document = page_musicxml([StaffTranscription(number=1, musicxml=a_staff_transcription())])

    assert document.startswith('<?xml version="1.0" encoding="UTF-8"?>')


# --- configuration -----------------------------------------------------------


def test_a_model_is_configured_as_name_at_version() -> None:
    model = model_reference("ayce-long@2026-08-03-192253-final")

    assert (model.name, model.version) == ("ayce-long", "2026-08-03-192253-final")


@pytest.mark.parametrize("reference", ["ayce-long", "@1.0.0", "ayce-long@", ""])
def test_a_malformed_model_reference_is_refused(reference: str) -> None:
    with pytest.raises(ValueError, match="name@version"):
        model_reference(reference)


def test_a_malformed_model_reference_stops_the_process_at_startup() -> None:
    # Rather than becoming a Pipeline that announces itself and then times out
    # every execution it is given.
    with pytest.raises(ValueError, match="name@version"):
        OmniOmrSettings.for_testing(staff_model="no-version-here")


def test_the_defaults_name_the_models_the_development_stack_runs() -> None:
    settings = OmniOmrSettings.for_testing()

    assert model_reference(settings.layout_model).name == "dvorak-ola"
    assert model_reference(settings.staff_model).name == "ayce-long"


def test_the_default_pipeline_names_are_the_ones_the_web_ui_offers() -> None:
    # `components/web-ui/src/pipelines.ts` names these two outright: they are a
    # product decision rather than something a listing could express, so an
    # instance whose defaults drift stops offering them on the landing page.
    settings = OmniOmrSettings.for_testing()

    assert (settings.page_pipeline_name, settings.page_pipeline_version) == ("mzk-page", "1")
    assert (settings.staff_pipeline_name, settings.staff_pipeline_version) == ("mzk-staff", "1")
