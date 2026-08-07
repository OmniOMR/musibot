"""Writing what was found as a Musicorpus `layout.json`.

`layout.json` is a COCO object-detection document, and the *Musicorpus
Specification* defines it by analogy with `coco-object-detection.json`: the same
skeleton of `info`, `licenses`, `images`, `annotations` and `categories`, with a
vocabulary of page-structure objects instead of notation symbols.

That specification describes a *dataset*, though, and this file is written into
a working *Musicorpus Page* that belongs to a *User* and is thrown away when
they are done with it. Two of its dataset-level fields therefore have no honest
value here, and are left out rather than invented — see the README.
"""

from __future__ import annotations

from datetime import date, timezone
from datetime import datetime as DateTime
from typing import Any

from dvorak_ola.categories import CATEGORY_ID
from dvorak_ola.detector import Detection, PageDetections

REPOSITORY_URL = "https://github.com/v-dvorak/omr-layout-analysis"

CONTRIBUTOR = "Vojtěch Dvořák, Institute of Formal and Applied Linguistics, Charles University"


def layout_document(
    image_file: str,
    page: PageDetections,
    model_name: str,
    model_version: str,
    created_on: date | None = None,
) -> dict[str, Any]:
    """Build the whole document for one page image."""
    created_on = created_on or DateTime.now(timezone.utc).date()

    annotations = [
        _annotation(annotation_id, detection)
        for annotation_id, detection in enumerate(_ordered(page.detections))
    ]

    return {
        "info": {
            "year": created_on.year,
            "version": "1.0",
            "description": f"{model_name} {model_version}",
            "contributor": CONTRIBUTOR,
            "url": REPOSITORY_URL,
            "date_created": created_on.strftime("%Y/%m/%d"),
        },
        "images": [
            {
                "id": 0,
                "width": page.image_width,
                "height": page.image_height,
                "file_name": image_file,
            }
        ],
        "annotations": annotations,
        "categories": _categories_used(page.detections),
    }


def _ordered(detections: list[Detection]) -> list[Detection]:
    """Put the annotations in reading order, within a class, per page.

    Nothing reads this ordering and nothing should — a COCO file is a set of
    annotations. It is imposed so that running the same model over the same page
    twice produces the same bytes, which makes the output diffable and a
    regression visible; and, having to pick some order, down-the-page beats the
    order confidence happened to come out in for anyone reading the file.
    """
    return sorted(
        detections,
        key=lambda detection: (
            CATEGORY_ID[detection.category],
            detection.y,
            detection.x,
        ),
    )


def _annotation(annotation_id: int, detection: Detection) -> dict[str, Any]:
    """One annotation.

    `area` and `segmentation` are both derived from the box, as the
    specification says they are for a layout file: the area is the box's area
    rather than a mask's, and the segmentation is exactly the rectangle the box
    describes, corners in the same order the specification's own example uses.
    """
    x, y, width, height = detection.x, detection.y, detection.width, detection.height

    return {
        "id": annotation_id,
        "image_id": 0,
        "category_id": CATEGORY_ID[detection.category],
        "segmentation": [[x, y, x, y + height, x + width, y + height, x + width, y]],
        "area": width * height,
        "bbox": [x, y, width, height],
        "iscrowd": 0,
        # Beyond the specification, which says nothing about confidence because
        # it describes hand-checked ground truth. This is a prediction, and the
        # number is kept because a Pipeline downstream can only ever re-threshold
        # upwards — whatever is dropped here is gone, and dropping the score
        # along with it would force a second forward pass to get it back.
        "score": detection.score,
    }


def _categories_used(detections: list[Detection]) -> list[dict[str, Any]]:
    """The categories this page actually has, which is what the spec asks for."""
    used = {detection.category for detection in detections}
    return [
        {"id": CATEGORY_ID[name], "name": name}
        for name in sorted(used, key=lambda name: CATEGORY_ID[name])
    ]


def summarise(detections: list[Detection]) -> str:
    """A one-line count per category, for the log — `12 staff, 3 system`."""
    if not detections:
        return "nothing"

    counts: dict[str, int] = {}
    for detection in detections:
        counts[detection.category] = counts.get(detection.category, 0) + 1

    return ", ".join(
        f"{counts[name]} {name}" for name in sorted(counts, key=lambda name: CATEGORY_ID[name])
    )
