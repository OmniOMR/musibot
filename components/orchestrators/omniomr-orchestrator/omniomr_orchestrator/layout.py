"""Reading the staves out of a Musicorpus `layout.json`.

`layout.json` is a COCO object-detection document (see the *Musicorpus
Specification*, and `components/models/dvorak-ola` for the *Model* that writes
the one this *Pipeline* consumes). This turns its boxes into the instruments
they belong to, the way a human reads a page of orchestral music: down each
system, then across systems, following the same instrument top to bottom.
"""

from dataclasses import dataclass
from itertools import zip_longest
from typing import Any, TypeVar
from collections.abc import Iterator

from .errors import UnreadableLayout


STAFF_CATEGORY = "staff"
"""What the *Musicorpus Specification* calls one staff carrying music. The
category *id* is deliberately not hard-coded: a document says which id it used,
and reading that is the difference between working with any producer and
working with one."""
GRAND_STAFF_CATEGORY = "grandstaff"
"""A brace joining two staffs of one instrument (piano, harp, organ) into a
single grand staff. Its box is expected to vertically span both staffs it
joins."""
SYSTEM_CATEGORY = "system"
"""One line of music across the page: every instrument playing at once, boxed
together. Its box is expected to vertically span every staff playing in it."""

RETRIEVED_LAYOUT_CATEGORIES = {STAFF_CATEGORY, GRAND_STAFF_CATEGORY, SYSTEM_CATEGORY}


@dataclass(frozen=True)
class BoundingBox:
    """One box, in pixels of the page image."""

    left: int
    top: int
    width: int
    height: int

    @property
    def bottom(self) -> int:
        return self.top + self.height

    @property
    def right(self) -> int:
        return self.left + self.width

    def vertical_overlap(self, other: "BoundingBox") -> int:
        """How many pixels of height this box and `other` share."""
        return max(0, min(self.bottom, other.bottom) - max(self.top, other.top))


@dataclass(frozen=True)
class StaffBox(BoundingBox):
    number: int


@dataclass(frozen=True)
class _StaffBoxLoad(BoundingBox):
    pass


def _staff_box_from_load(number: int, box: _StaffBoxLoad) -> StaffBox:
    return StaffBox(box.left, box.top, box.width, box.height, number)


@dataclass(frozen=True)
class GrandStaffBox(BoundingBox):
    pass


@dataclass(frozen=True)
class SystemBox(BoundingBox):
    pass


@dataclass
class Instrument:
    """One instrument, as it recurs from system to system down the page.

    `occurrences` maps a system number (0-based, matching the system's
    position in top-to-bottom reading order) to that instrument's staffs in
    that system — one staff for a single-staff instrument, two for a grand
    staff. A system the instrument doesn't appear in simply has no key,
    rather than the entry being padded or the systems after it shifting out
    of alignment.
    """

    occurrences: dict[int, list[StaffBox]]

    @property
    def top(self) -> int:
        first_system = min(self.occurrences)
        return self.occurrences[first_system][0].top

    @property
    def is_grand_staff(self) -> bool:
        first_system = min(self.occurrences)
        return len(self.occurrences[first_system]) == 2

    def all_staffs(self) -> list[StaffBox]:
        return [staff for occurrence in self.occurrences.values() for staff in occurrence]

    def __str__(self) -> str:
        ordered = [self.occurrences[system] for system in sorted(self.occurrences)]
        if not self.is_grand_staff:
            staff_repr = f"[{', '.join(str(s[0].number) for s in ordered)}]"
        else:
            staff_repr = f"[{', '.join(f'({s[0].number}, {s[1].number})' for s in ordered)}]"
        return f"{type(self).__name__}({staff_repr})"


@dataclass(frozen=True)
class PageLayout:
    instruments: list[Instrument]

    @property
    def staff_count(self) -> int:
        return sum(
            sum(len(occurrence) for occurrence in instrument.occurrences.values())
            for instrument in self.instruments
        )

    def staff_ordering(self) -> list[list[list[int]]]:
        return [
            [[s.number for s in x.occurrences[system]] for system in sorted(x.occurrences)]
            for x in self.instruments
        ]

    def get_all_staffs(self) -> list[StaffBox]:
        return sorted(
            [x for instrument in self.instruments for x in instrument.all_staffs()],
            key=lambda s: s.top,
        )

    def __iter__(self) -> Iterator[Instrument]:
        return (i for i in self.instruments)

    @property
    def system_count(self) -> int:
        if not self.instruments:
            return 0
        return max(max(i.occurrences) for i in self.instruments) + 1

    def get_staffs_in_system(self, system_number: int) -> list[list[StaffBox]]:
        """
        Retrieves all staffs in a page that belong to the system.
        1-based.

        A dictionary lookup by system number, not a positional one: an
        instrument missing from this system (e.g. one voice dropping out
        partway through the score) is simply absent from the result,
        instead of the lookup drifting onto some other instrument's staff.
        """
        index_num = system_number - 1
        return [
            instrument.occurrences[index_num]
            for instrument in self.instruments
            if index_num in instrument.occurrences
        ]

    def __str__(self) -> str:
        return f"{type(self).__name__}(instrument_count={len(self.instruments)}, instruments=[{', '.join(str(i) for i in self.instruments)}])"


T = TypeVar("T", bound=BoundingBox)


def layout_to_instruments(layout: dict[str, Any]) -> PageLayout:
    """Every instrument on the page, top to bottom, each with its staffs.

    Mirrors reading an orchestral score: staffs are grouped into systems,
    systems into instruments (pairing up grand staffs), and the same
    instrument is then followed as it recurs, system after system, down
    the page.
    """
    staffs = staff_boxes(layout)
    grand_staffs = grand_staff_boxes(layout)

    if len(staffs) == 0 and len(grand_staffs) == 0:
        return PageLayout([])

    systems = system_boxes(layout)

    if not systems:
        # A page the model saw no system boxes on is still a page: treat it
        # as the one system spanning every staff found on it.
        systems = [_covering_box(staffs, SystemBox)]

    groups = _instrument_groups_by_system(staffs, grand_staffs, systems)
    instruments = _link_instruments(groups)
    instruments.sort(key=lambda instrument: instrument.top)
    return PageLayout(instruments)


def staff_boxes(layout: dict[str, Any]) -> list[StaffBox]:
    """Every `staff` in the document, in reading order with `number`."""
    staffs = _category_boxes(layout, STAFF_CATEGORY, _StaffBoxLoad)
    output: list[StaffBox] = []
    for i, staff in enumerate(staffs, start=1):
        output.append(_staff_box_from_load(i, staff))
    return output


def grand_staff_boxes(layout: dict[str, Any]) -> list[GrandStaffBox]:
    """Every `grandstaff` in the document, in reading order."""
    return _category_boxes(layout, GRAND_STAFF_CATEGORY, GrandStaffBox)


def system_boxes(layout: dict[str, Any]) -> list[SystemBox]:
    """Every `system` in the document, in reading order."""
    return _category_boxes(layout, SYSTEM_CATEGORY, SystemBox)


def _instrument_groups_by_system(
    staffs: list[StaffBox],
    grand_staffs: list[GrandStaffBox],
    systems: list[SystemBox],
) -> list[list[list[StaffBox]]]:
    """Each system's staffs, split into instruments, in top-to-bottom system order.

    Format: systems -> instruments -> staffs — the box equivalent of the old
    `get_instrument_groups_from_systems`. A system's *position* in this list
    is what `_link_instruments` later uses as that system's number, so every
    system — including the orphan, one-staff systems `_assign_to_systems`
    invents for staffs outside any detected system box — is sorted by
    vertical position here, before that number gets assigned. Without this,
    an orphan system tacked onto the end would get a system number that
    doesn't reflect where it actually sits on the page.
    """
    staffs_by_system = _assign_to_systems(staffs, systems)
    grand_staffs_by_system = _assign_to_systems(grand_staffs, systems, required=False)

    # `staffs_by_system` can be longer than `systems` — each staff that
    # overlaps no system became its own trailing singleton group.
    # `grand_staffs_by_system` never grows past `len(systems)` since orphan
    # grand-staffs are simply dropped, not required=True. zip_longest keeps
    # those trailing orphan-staff systems instead of `zip` truncating them.
    groups = [
        _instruments_in_system(system_staffs, system_grand_staffs)
        for system_staffs, system_grand_staffs in zip_longest(
            staffs_by_system, grand_staffs_by_system, fillvalue=[]
        )
    ]

    groups = [group for group in groups if group]
    groups.sort(key=lambda group: min(instrument[0].top for instrument in group))

    return groups


def _instruments_in_system(
    staffs: list[StaffBox],
    grand_staffs: list[GrandStaffBox],
) -> list[list[StaffBox]]:
    """One system's staffs, paired up under any grand staff box that spans two of them.

    A staff not covered by any grand staff is its own single-staff
    instrument — the box equivalent of a staff with no grouping bracket.
    """
    instruments: list[list[StaffBox]] = []
    claimed: set[int] = set()

    for grand_staff in grand_staffs:
        spanned = [
            staff
            for staff in staffs
            if id(staff) not in claimed and grand_staff.vertical_overlap(staff) > 0
        ]
        if len(spanned) == 2:
            spanned.sort(key=lambda staff: staff.top)
            instruments.append(spanned)
            claimed.update(id(staff) for staff in spanned)
        # A grand-staff box spanning anything other than exactly two free
        # staffs is noise (or already-claimed staffs) and is dropped, same
        # as the old code silently ignoring non-2-staff groupings.

    for staff in staffs:
        if id(staff) not in claimed:
            instruments.append([staff])
            claimed.add(id(staff))

    instruments.sort(key=lambda instrument: instrument[0].top)

    assert sum(len(instrument) for instrument in instruments) == len(staffs), (
        "Every staff in a system must end up in exactly one instrument"
    )

    return instruments


def _link_instruments(groups: list[list[list[StaffBox]]]) -> list[Instrument]:
    """Follows each instrument as it recurs, system after system, down the page.

    Instruments are aligned starting from the system with the most of
    them — the fullest picture of the ensemble — matching each other
    system's instruments into the closest slot of the same kind (grand
    staff or not). `groups`' index for a system, assigned in
    `_instrument_groups_by_system`, is what each match gets recorded under,
    so a system missing an instrument partway down the page leaves a gap in
    that instrument's `occurrences` rather than shifting anything else.
    """
    indexed_groups = [(system, group) for system, group in enumerate(groups) if group]
    if not indexed_groups:
        return []

    indexed_groups.sort(key=lambda entry: len(entry[1]), reverse=True)

    reference_system, reference_group = indexed_groups[0]
    output: list[dict[int, list[StaffBox]]] = [
        {reference_system: instrument} for instrument in reference_group
    ]

    for system, instruments in indexed_groups[1:]:
        output = _add_system_to_output(output, system, instruments)

    return [Instrument(occurrences=occurrences) for occurrences in output]


def _add_system_to_output(
    output: list[dict[int, list[StaffBox]]],
    system: int,
    instruments: list[list[StaffBox]],
) -> list[dict[int, list[StaffBox]]]:
    """Slots one system's instruments into `output`, matching by staff count.

    Walks both in reading order, advancing through `output` until it finds
    the next slot of the same kind (grand staff or not, judged by that
    instrument's earliest-known occurrence) as the instrument being placed,
    so an instrument that's missing from a system doesn't shift everything
    after it out of alignment. Each match is recorded under `system` rather
    than appended positionally, so occurrences can later be looked up by
    system number even when a system in the middle of the score is missing
    an instrument.
    """
    index = 0
    for instrument in instruments:
        while index < len(output) and _instrument_size(output[index]) != len(instrument):
            index += 1
        if index < len(output):
            output[index][system] = instrument
        else:
            output.append({system: instrument})
        index += 1

    return output


def _instrument_size(occurrences: dict[int, list[StaffBox]]) -> int:
    """1 for a single-staff instrument, 2 for a grand staff, going by its earliest occurrence."""
    earliest_system = min(occurrences)
    return len(occurrences[earliest_system])


def _assign_to_systems(
    boxes: list[T],
    systems: list[SystemBox],
    required: bool = True,
) -> list[list[T]]:
    """Distributes `boxes` among `systems`, each going to whichever it overlaps most vertically.

    A `required` box that overlaps no system (including when there are no
    systems at all) becomes a system of its own — one staff with no system
    box around it is still a system, just of one.
    """
    grouped: list[list[T]] = [[] for _ in systems]

    for box in boxes:
        overlaps = [system.vertical_overlap(box) for system in systems]
        best = max(range(len(systems)), key=lambda i: overlaps[i]) if systems else -1
        if best == -1 or overlaps[best] == 0:
            if required:
                grouped.append([box])
            continue
        grouped[best].append(box)

    return [sorted(group, key=lambda box: box.top) for group in grouped]


def _covering_box(boxes: list[T], box_cls: type) -> Any:
    """The smallest box containing every one of `boxes`."""
    left = min(box.left for box in boxes)
    top = min(box.top for box in boxes)
    right = max(box.right for box in boxes)
    bottom = max(box.bottom for box in boxes)
    return box_cls(left=left, top=top, width=right - left, height=bottom - top)


def _category_boxes(layout: dict[str, Any], category_name: str, box_cls: type) -> list[Any]:
    """Every annotation of `category_name`, as `box_cls`, in reading order."""
    category_ids = {
        category["id"]
        for category in _listing(layout, "categories")
        if isinstance(category, dict) and category.get("name") == category_name
    }

    if not category_ids:
        # Either the page genuinely has none of these — the model lists only
        # the categories a page actually has — or the document is not a
        # layout at all. The caller tells those apart by the count, so this
        # is not an error here.
        return []

    boxes = [
        _bounding_box(annotation["bbox"], box_cls)
        for annotation in _listing(layout, "annotations")
        if isinstance(annotation, dict) and annotation.get("category_id") in category_ids
    ]

    return sorted(boxes, key=lambda box: (box.top, box.left))


def _listing(layout: dict[str, Any], field: str) -> list[Any]:
    value = layout.get(field, [])
    if not isinstance(value, list):
        raise UnreadableLayout(f"The layout file's {field!r} is not a list")
    return value


def _bounding_box(bbox: Any, box_cls: type) -> Any:
    """One COCO `bbox`, which is `[x, y, width, height]` and nothing else."""
    if not isinstance(bbox, list) or len(bbox) != 4:
        raise UnreadableLayout(f"A box's bbox is not [x, y, width, height]: {bbox!r}")

    try:
        left, top, width, height = (round(float(value)) for value in bbox)
    except (TypeError, ValueError):
        raise UnreadableLayout(f"A box's bbox is not made of numbers: {bbox!r}")

    return box_cls(left=left, top=top, width=width, height=height)
