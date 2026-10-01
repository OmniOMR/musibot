"""The parts of `mzk` that are not the pipeline: layout and slicing.

These are the pieces that will move into a Musicorpus library when there is one,
so they are tested as the plain functions they are.
"""

import json

import pytest

from omniomr_orchestrator import OmniOmrSettings, model_reference
from omniomr_orchestrator.errors import UnreadableLayout
from omniomr_orchestrator.layout import BoundingBox, StaffBox, staff_boxes
from omniomr_orchestrator.slicing import UnreadableImage, crop_staff, decode_page, slice_page
from tests.fakes import a_layout, a_page

# --- reading the layout ------------------------------------------------------


def test_it_reads_the_staff_boxes_in_reading_order() -> None:
    layout = json.loads(a_layout((10, 200, 100, 20), (10, 50, 100, 20), (200, 50, 100, 20)))

    assert staff_boxes(layout) == [
        StaffBox(10, 50, 100, 20, number=1),
        StaffBox(200, 50, 100, 20, number=2),
        StaffBox(10, 200, 100, 20, number=3),
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

    assert staff_boxes(layout) == [StaffBox(10, 10, 100, 20, number=1)]


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

    assert staff_boxes(layout) == [StaffBox(10, 11, 100, 20, number=1)]


# --- slicing -----------------------------------------------------------------


def test_a_crop_is_the_box_plus_a_share_of_its_own_height() -> None:
    page = decode_page(a_page(400, 300))

    crop = crop_staff(page, BoundingBox(100, 100, 200, 40), padding_ratio=0.25)

    assert crop.shape[:2] == (60, 220)  # 40 + 2*10 tall, 200 + 2*10 wide


def test_a_crop_at_the_edge_is_clamped_to_the_page() -> None:
    page = decode_page(a_page(400, 300))

    crop = crop_staff(page, BoundingBox(0, 0, 400, 40), padding_ratio=0.5)

    assert crop.shape[:2] == (60, 400)  # 20px below, nothing above or beside


def test_a_box_outside_the_page_is_refused_legibly() -> None:
    page = decode_page(a_page(400, 300))

    with pytest.raises(UnreadableImage, match="does not overlap"):
        crop_staff(page, BoundingBox(500, 500, 100, 20), padding_ratio=0.0)


def test_something_that_is_not_an_image_is_refused_legibly() -> None:
    with pytest.raises(UnreadableImage, match="could not be decoded"):
        decode_page(b"this is not a JPEG")


def test_slicing_a_page_returns_one_jpeg_per_box() -> None:
    crops = slice_page(a_page(), [BoundingBox(10, 10, 100, 20), BoundingBox(10, 50, 100, 20)], 0.0)

    assert len(crops) == 2
    assert all(crop.startswith(b"\xff\xd8") for crop in crops)  # JPEG's magic


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
