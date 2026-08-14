"""Reading the staves out of a Musicorpus `layout.json`.

`layout.json` is a COCO object-detection document (see the *Musicorpus
Specification*, and `components/models/dvorak-ola` for the *Model* that writes
the one this *Pipeline* consumes). All this needs from it is the boxes of one
category, in the order a human would read them.
"""

from dataclasses import dataclass
from typing import Any

STAFF_CATEGORY = "staff"
"""What the *Musicorpus Specification* calls one staff carrying music. The
category *id* is deliberately not hard-coded: a document says which id it used,
and reading that is the difference between working with any producer and
working with one."""


class UnreadableLayout(ValueError):
    """The `layout.json` is not one this *Pipeline* can slice a page along.

    Raised with a message written for the *User* who will see it, since a
    *Pipeline Execution's* error is what reaches them.
    """


@dataclass(frozen=True)
class StaffBox:
    """One staff, in pixels of the page image."""

    x: int
    y: int
    width: int
    height: int

    @property
    def bottom(self) -> int:
        return self.y + self.height

    @property
    def right(self) -> int:
        return self.x + self.width


def staff_boxes(layout: dict[str, Any]) -> list[StaffBox]:
    """Every `staff` in the document, in reading order.

    Reading order is down the page and then across, which is what a
    single-column page of music means by it. A page laid out in two columns
    would need the columns found first; that is a real limitation and not one
    this pipeline pretends to handle — see the README.
    """
    category_ids = {
        category["id"]
        for category in _listing(layout, "categories")
        if isinstance(category, dict) and category.get("name") == STAFF_CATEGORY
    }

    if not category_ids:
        # Either the page genuinely has no staves — the model lists only the
        # categories a page actually has — or the document is not a layout at
        # all. The caller tells those apart by the count, so this is not an
        # error here.
        return []

    boxes = [
        _staff_box(annotation["bbox"])
        for annotation in _listing(layout, "annotations")
        if isinstance(annotation, dict) and annotation.get("category_id") in category_ids
    ]

    return sorted(boxes, key=lambda box: (box.y, box.x))


def _listing(layout: dict[str, Any], field: str) -> list[Any]:
    value = layout.get(field, [])
    if not isinstance(value, list):
        raise UnreadableLayout(f"The layout file's {field!r} is not a list")
    return value


def _staff_box(bbox: Any) -> StaffBox:
    """One COCO `bbox`, which is `[x, y, width, height]` and nothing else."""
    if not isinstance(bbox, list) or len(bbox) != 4:
        raise UnreadableLayout(f"A staff's bbox is not [x, y, width, height]: {bbox!r}")

    try:
        x, y, width, height = (round(float(value)) for value in bbox)
    except (TypeError, ValueError):
        raise UnreadableLayout(f"A staff's bbox is not made of numbers: {bbox!r}")

    return StaffBox(x=x, y=y, width=width, height=height)
