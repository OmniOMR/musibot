"""The COCO document: that it says what the Musicorpus Specification asks for."""

from __future__ import annotations

from datetime import date
from typing import Any

from fake_detector import a_detection, a_page

from dvorak_ola.detector import Detection
from dvorak_ola.layout import layout_document, summarise


def a_document(
    *detections: Detection,
    image_width: int = 1000,
    image_height: int = 1400,
) -> dict[str, Any]:
    return layout_document(
        "image.jpg",
        a_page(list(detections) or [a_detection()], image_width, image_height),
        "dvorak-ola",
        "2.0-2025-03-09",
        created_on=date(2026, 8, 7),
    )


def test_it_is_a_coco_document_about_one_image() -> None:
    document = a_document(image_width=2480, image_height=3508)

    assert document["images"] == [
        {"id": 0, "width": 2480, "height": 3508, "file_name": "image.jpg"}
    ]
    assert all(annotation["image_id"] == 0 for annotation in document["annotations"])


def test_the_info_block_names_what_produced_the_file() -> None:
    # A Musicorpus Page is not a dataset, so these dataset-level fields describe
    # the producer instead — which is the useful thing to know about a file that
    # a model wrote rather than a person.
    info = a_document()["info"]

    assert info["description"] == "dvorak-ola 2.0-2025-03-09"
    assert info["date_created"] == "2026/08/07"
    assert info["year"] == 2026


def test_an_annotation_derives_area_and_segmentation_from_its_box() -> None:
    [annotation] = a_document(a_detection(x=10, y=20, width=300, height=40))["annotations"]

    assert annotation["bbox"] == [10, 20, 300, 40]
    assert annotation["area"] == 300 * 40
    assert annotation["segmentation"] == [[10, 20, 10, 60, 310, 60, 310, 20]]
    assert annotation["iscrowd"] == 0


def test_the_confidence_is_kept_beside_each_box() -> None:
    [annotation] = a_document(a_detection(score=0.87))["annotations"]

    assert annotation["score"] == 0.87


def test_categories_use_fixed_ids_and_list_only_what_was_found() -> None:
    document = a_document(a_detection("systemMeasure"), a_detection("staff"))

    assert document["categories"] == [
        {"id": 0, "name": "staff"},
        {"id": 6, "name": "systemMeasure"},
    ]


def test_a_page_with_nothing_on_it_is_still_a_valid_document() -> None:
    # A cover or a title page is a real thing to hand this model, and the
    # checkpoint was trained on a thousand of them on purpose.
    document = layout_document(
        "image.jpg", a_page([]), "dvorak-ola", "2.0-2025-03-09", created_on=date(2026, 8, 7)
    )

    assert document["annotations"] == []
    assert document["categories"] == []


def test_annotations_are_ordered_by_category_then_down_the_page() -> None:
    document = a_document(
        a_detection("system", y=500),
        a_detection("staff", y=900, x=10),
        a_detection("staff", y=100),
        a_detection("staff", y=900, x=5),
    )

    assert [
        (annotation["category_id"], annotation["bbox"][1], annotation["bbox"][0])
        for annotation in document["annotations"]
    ] == [(0, 100, 10), (0, 900, 5), (0, 900, 10), (3, 500, 10)]


def test_annotation_ids_are_unique_and_follow_that_order() -> None:
    document = a_document(a_detection("system"), a_detection("staff"), a_detection("staff"))

    assert [annotation["id"] for annotation in document["annotations"]] == [0, 1, 2]


def test_the_log_line_counts_each_category() -> None:
    assert summarise([a_detection("staff"), a_detection("staff"), a_detection("system")]) == (
        "2 staff, 1 system"
    )
    assert summarise([]) == "nothing"
