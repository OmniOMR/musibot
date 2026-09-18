"""Gluing staff transcriptions into one page-level MusicXML file.

The page's instruments, as the layout *Model* reports them, each become one
`<part>`. An instrument's measures are appended in reading order, system after
system, with an explicit system break where each new system begins.

Like the slicing, this is *Musicorpus* logic rather than *Musibot* logic and
will move to a library of its own when there is one.
"""

from dataclasses import dataclass
import traceback
from xml.etree import ElementTree as ET
from lmx.musicxml.grandstaff.zip_grandstaff import zip_grandstaff
from typing import TypeAlias

from omniomr_orchestrator.layout import Instrument, PageLayout, StaffBox
from musibot.orchestrator_head import PipelineContext

from .errors import UnreadableTranscription

MUSICXML_VERSION = "4.0"

MEASURE_REST_DURATION = "4"

GRAND_STAFF_FILLER_PART_ID = "GS_FILLER"
EMPTY_STAFF_PART_ID = "BROKEN_GS"
ZIPPED_GRAND_STAFF_PART_ID = "PLACEHOLDER"


@dataclass(frozen=True)
class StaffTranscription:
    """What became of one staff.

    A staff that failed carries the reason instead of a transcription, and
    still takes up a system in the page — one measure saying so, rather than
    nothing, because a page that silently skips a staff reads as music that was
    never there.
    """

    number: int
    musicxml: str | None = None
    error: str | None = None

    @property
    def transcribed(self) -> bool:
        return self.musicxml is not None


# A staff number to its parsed transcription, or to None where the staff has
# none. The distinction matters at every use site, so the key is always
# present and only the value goes missing.
TranscriptionLookup: TypeAlias = dict[int, ET.Element | None]


def page_musicxml(
    ctx: PipelineContext, staves: list[StaffTranscription], page_layout: PageLayout
) -> str:
    """One `score-partwise` document holding every staff, one after another."""
    if not staves:
        raise UnreadableTranscription("A page needs at least one staff to be written")

    lookup = _transcription_lookup(staves)
    expected_measures_by_system = _expected_measures_by_system(page_layout, lookup)

    ctx.logger.info(f"Expected measure counts in each system: {expected_measures_by_system}")

    score = ET.Element("score-partwise", {"version": MUSICXML_VERSION})
    _append_part_list(score, page_layout)

    for id_, instrument in enumerate(page_layout, start=1):
        part = ET.SubElement(score, "part", {"id": f"P{id_}"})
        _append_instrument_measures(ctx, part, instrument, lookup, expected_measures_by_system)

    ET.indent(score, space="  ")
    body = ET.tostring(score, encoding="unicode")
    return f'<?xml version="1.0" encoding="UTF-8"?>\n{body}\n'


def _transcription_lookup(staves: list[StaffTranscription]) -> TranscriptionLookup:
    """Staff numbers to their parsed transcriptions."""
    lookup: TranscriptionLookup = {}

    for staff in staves:
        if staff.musicxml is None:
            lookup[staff.number] = None
            continue

        try:
            lookup[staff.number] = ET.fromstring(staff.musicxml)
        except ET.ParseError as error:
            raise UnreadableTranscription(
                f"The transcription of staff {staff.number} is not valid XML: {error}"
            )

    return lookup


def _expected_measures_by_system(
    page_layout: PageLayout, lookup: TranscriptionLookup
) -> dict[int, int]:
    """How many measures each system is taken to have. System numbers are 1-based.

    Staves sharing a system must end up with the same number of measures, so
    the longest transcription in a system sets the count and the rest are
    padded up to it.
    """
    expected_measures_by_system: dict[int, int] = {}

    for system_number in range(1, page_layout.system_count + 1):
        staff_ids = [x.number for xs in page_layout.get_staffs_in_system(system_number) for x in xs]
        staff_mxml = [lookup[num] for num in staff_ids if lookup[num] is not None]
        expected_measure_count = max(
            len(source.findall(".//part/measure")) if source is not None else 0
            for source in staff_mxml
        )
        expected_measures_by_system[system_number] = max(1, expected_measure_count)

    return expected_measures_by_system


def _append_part_list(score: ET.Element, page_layout: PageLayout) -> None:
    """The `<part-list>` head: one `<score-part>` per instrument on the page."""
    part_list = ET.SubElement(score, "part-list")

    for id_, instrument in enumerate(page_layout, start=1):
        score_part = ET.SubElement(part_list, "score-part", {"id": f"P{id_}"})
        part_name = ET.SubElement(score_part, "part-name", {"print-object": "no"})

        if instrument.is_grand_staff:
            part_name.text = "Grand Staff"
        else:
            part_name.text = "Staff"


def _append_instrument_measures(
    ctx: PipelineContext,
    part: ET.Element,
    instrument: Instrument,
    lookup: TranscriptionLookup,
    expected_measures_by_system: dict[int, int],
) -> None:
    """Every measure one instrument contributes, system by system down the page."""
    number = 0  # tracks the number of already written measures

    for system_number in sorted(expected_measures_by_system.keys()):
        expected = expected_measures_by_system[system_number]
        box_staffs = instrument.occurrences.get(system_number - 1)

        if box_staffs is not None:
            staff, staff_number = _transcribed_instrument_staff(
                ctx, instrument, box_staffs, lookup, expected, first_of_page=number == 0
            )
        else:
            staff, staff_number = _undetected_instrument_staff(
                instrument, expected, first_of_page=number == 0
            )

        for position, measure in enumerate(
            _measures(staff, staff_number=staff_number, expected=expected)
        ):
            number += 1
            # Renumbered across the whole page: every staff transcription counts
            # its own measures from 1, so keeping them would number the page
            # 1, 2, 1, 2, 3, 1 — and a measure number is what a person quotes
            # when they tell you where the recognition went wrong.
            measure.set("number", str(number))

            if position == 0 and number > 1:
                # Where this staff began on the page. It is a `<print>` rather
                # than anything structural, so a reader that ignores layout
                # still sees one continuous piece of music.
                measure.insert(0, ET.Element("print", {"new-system": "yes"}))

            part.append(measure)


def _transcribed_instrument_staff(
    ctx: PipelineContext,
    instrument: Instrument,
    box_staffs: list[StaffBox],
    lookup: TranscriptionLookup,
    expected: int,
    *,
    first_of_page: bool,
) -> tuple[ET.Element, int]:
    """One system of an instrument the layout did detect.

    Returns the element its measures are read out of, and the staff number to
    name in any error about them.
    """
    upper_box = box_staffs[0]
    upper_staff = lookup[upper_box.number]

    if instrument.is_grand_staff:
        staff = _grand_staff_instrument(
            ctx, box_staffs, lookup, expected, first_of_page=first_of_page
        )
    else:
        staff = _single_staff_instrument(
            ctx, upper_box, upper_staff, expected, first_of_page=first_of_page
        )

    return staff, upper_box.number


def _grand_staff_instrument(
    ctx: PipelineContext,
    box_staffs: list[StaffBox],
    lookup: TranscriptionLookup,
    expected: int,
    *,
    first_of_page: bool,
) -> ET.Element:
    """Two staffs identified as piano, zipped back into a single grand staff."""
    upper_box, lower_box = box_staffs[0], box_staffs[1]
    upper_staff = lookup[upper_box.number]
    lower_staff = lookup[lower_box.number]

    ctx.logger.info(f"Writing {', '.join([str(s.number) for s in box_staffs])} as a grand staff")

    # --- 1. Fix potentially missing staffs, catch staffs with no measures,
    #        strip the model output to contain "<part>" only.

    # For zipping two staffs into one grand staff, the staffs have to be
    # passed as two "<part>"s. Here, the parts are built as an unreadable
    # staff (if the part is None) or stripped from the model output down to
    # their "<part>" content.
    _upper_part = _grand_staff_part(upper_staff, upper_box.number)
    _lower_part = _grand_staff_part(lower_staff, lower_box.number)

    # --- 2. Add empty measure to the end of a shorter staff, if it is missing
    measure_difference = len(_upper_part) - len(_lower_part)

    # More measures in the lower part, add to upper part
    if measure_difference < 0:
        for _ in range(abs(measure_difference)):
            _upper_part.append(_missing_measure(first_of_page=False))
        ctx.logger.info(
            f"Extended staff {upper_box.number} by {abs(measure_difference)} measure{'s' if abs(measure_difference) > 1 else ''}"
        )
    elif measure_difference > 0:
        for _ in range(measure_difference):
            _lower_part.append(_missing_measure(first_of_page=False))
        ctx.logger.info(
            f"Extended staff {lower_box.number} by {abs(measure_difference)} measure{'s' if abs(measure_difference) > 1 else ''}"
        )

    assert len(_upper_part) == len(_lower_part)

    # --- 3. Zip the two staffs into one grand staff
    try:
        gs = zip_grandstaff(
            _upper_part,
            _lower_part,
            output_part_id=ZIPPED_GRAND_STAFF_PART_ID,
        )
    except AssertionError as _:
        ctx.logger.info(traceback.format_exc())
        ctx.logger.info(f"Cannot zip grand staff ({upper_box.number}, {lower_box.number})")
        gs = _empty_staff(
            True,
            expected,
            message=f"Cannot zip grand staff {(upper_box.number, lower_box.number)}",
            first_of_page=first_of_page,
        )

    # --- 4. Wrap the final grand staff inside a "<wrap>" element; the
    #        "find(...)" method in "_measures(...)" won't work otherwise.
    #        !! Note that this grand staff MusicXML is missing "<part-list>",
    #        the xml version element etc. However, these elements are not
    #        needed further down the pipeline.
    return _wrapped(gs)


def _grand_staff_part(staff: ET.Element | None, staff_number: int) -> ET.Element:
    """One half of a grand staff, as the bare `<part>` that `zip_grandstaff` expects."""
    if staff is None:
        return _replace_broken_staff_in_gs(staff_number)

    part = staff.find(".//part")
    if part is None:
        raise UnreadableTranscription(
            f"The transcription of staff {staff_number} contains no measures"
        )

    return part


def _replace_broken_staff_in_gs(number: int) -> ET.Element:
    """Unreadable measure with a tag wrapped inside its own "<part>" element."""
    part = ET.Element("part", {"id": GRAND_STAFF_FILLER_PART_ID})
    part.append(_unreadable_staff(number, first_of_page=True))
    return part


def _single_staff_instrument(
    ctx: PipelineContext,
    upper_box: StaffBox,
    upper_staff: ET.Element | None,
    expected: int,
    *,
    first_of_page: bool,
) -> ET.Element:
    """One unbraced staff of one system."""
    ctx.logger.info(f"Writing {upper_box.number} as a single staff")

    # The staff was detected, but cannot be transcribed
    if upper_staff is None:
        return _wrapped(
            _empty_staff(
                False,
                expected,
                message=f"Cannot transcribe staff {upper_box.number}",
                first_of_page=first_of_page,
            )
        )

    return upper_staff


def _undetected_instrument_staff(
    instrument: Instrument, expected: int, *, first_of_page: bool
) -> tuple[ET.Element, int]:
    """One system an instrument was not detected in, written as hidden measure rests.

    Two possible causes:
      - the staff was not found by the layout detector.
      - the staff is not there (the instrument is hidden).
    Either way, we will output it as hidden, using the "staff-details".
    """
    e_staff = _empty_staff(
        instrument.is_grand_staff,
        expected,
        hidden=True,
        first_of_page=first_of_page,
    )
    return _wrapped(e_staff), -1


def _wrapped(part: ET.Element) -> ET.Element:
    """A bare `<part>` under a `<wrap>` root, so `_measures` can find it."""
    wrap = ET.Element("wrap")
    wrap.append(part)
    return wrap


def _measures(source: ET.Element, staff_number: int, expected: int) -> list[ET.Element]:
    """The measures one staff contributes to the page."""
    # Every measure of every part, in document order. A staff transcription is
    # one part, so this is that part's measures — and a model that produced more
    # than one has them concatenated rather than silently dropped.

    measures = source.findall(".//part/measure")

    if not measures:
        raise UnreadableTranscription(
            f"The transcription of staff {staff_number} contains no measures"
        )

    if expected == -1:
        return measures

    return measures + [
        _missing_measure(first_of_page=False) for _ in range(expected - len(measures))
    ]


def _placeholder_measure(words_text: str, *, first_of_page: bool) -> ET.Element:
    """One measure of silence carrying a message printed above it.

    `divisions` and the rest's duration are both 1, so the measure is valid
    under whatever scale surrounds it.
    """
    measure = ET.Element("measure", {"number": "0"})

    if first_of_page:
        # Only here. `divisions` is carried forward from measure to measure, so
        # restating it mid-page would rewrite what every following duration
        # means — while a part that opens without it has no scale at all.
        attributes = ET.SubElement(measure, "attributes")
        divisions = ET.SubElement(attributes, "divisions")
        divisions.text = "1"

    direction = ET.SubElement(measure, "direction", {"placement": "above"})
    direction_type = ET.SubElement(direction, "direction-type")
    words = ET.SubElement(direction_type, "words")
    words.text = words_text

    note = ET.SubElement(measure, "note", {"print-object": "no"})
    ET.SubElement(note, "rest", {"measure": "yes"})
    # One division, whatever a division currently is: `measure="yes"` is what
    # carries the meaning, and any positive duration is valid under any scale.
    voice = ET.SubElement(note, "voice")
    voice.text = "1"

    return measure


def _unreadable_staff(staff_number: int, *, first_of_page: bool) -> ET.Element:
    """One measure standing in for a staff that has no transcription.

    It says so in the score itself, as a direction a renderer prints above the
    staff. An empty measure alone would be indistinguishable from a staff the
    *Model* read as silence, and telling a *User* that a page is silent where it
    was in fact unreadable is worse than telling them nothing.
    """
    return _placeholder_measure(
        f"Staff {staff_number} could not be transcribed", first_of_page=first_of_page
    )


def _missing_measure(*, first_of_page: bool) -> ET.Element:
    """One measure of padding, bringing a short staff up to its system's length."""
    return _placeholder_measure("Padding measure", first_of_page=first_of_page)


def _staff_base_attributes(is_grand_staff: bool) -> ET.Element:
    """An `<attributes>` head for a staff measure.

    Default clefs are G and F, keys are set to 0 fifths.
    """
    attrs = ET.Element("attributes")

    # Add base divisions
    ET.SubElement(attrs, "divisions").text = "1"

    # Add keys
    key1 = ET.SubElement(attrs, "key", {"number": "1", "print-object": "no"})
    ET.SubElement(key1, "fifths").text = "0"
    if is_grand_staff:
        key2 = ET.SubElement(attrs, "key", {"number": "2", "print-object": "no"})
        ET.SubElement(key2, "fifths").text = "0"

    # Add clefs
    clef1 = ET.SubElement(attrs, "clef", {"number": "1", "print-object": "no"})
    ET.SubElement(clef1, "sign").text = "G"
    ET.SubElement(clef1, "line").text = "2"
    if is_grand_staff:
        clef2 = ET.SubElement(attrs, "clef", {"number": "2", "print-object": "no"})
        ET.SubElement(clef2, "sign").text = "F"
        ET.SubElement(clef2, "line").text = "4"

    # Staff count
    if is_grand_staff:
        ET.SubElement(attrs, "staves").text = "2"

    return attrs


def _empty_staff(
    is_grand_staff: bool,
    expected_measure_count: int,
    hidden: bool = False,
    message: str | None = None,
    *,
    first_of_page: bool,
) -> ET.Element:
    """A `<part>` of measure rests, standing in for music that could not be written.

    `hidden` suppresses the staff entirely rather than printing empty bars,
    which is what an instrument absent from a system should look like.
    """
    part = ET.Element("part", {"id": EMPTY_STAFF_PART_ID})
    first = True

    for _ in range(expected_measure_count):
        measure = ET.SubElement(part, "measure")

        if first:
            if first_of_page:
                ET.SubElement(measure, "print", {"new-system": "yes"})
            measure.append(_staff_base_attributes(is_grand_staff))

            # Message cannot be printed, if the staff should be hidden
            if message is not None and not hidden:
                direction = ET.SubElement(measure, "direction", {"placement": "above"})
                direction_type = ET.SubElement(direction, "direction-type")
                words = ET.SubElement(direction_type, "words")
                words.text = message

            first = False

        if hidden:
            attrs = ET.SubElement(measure, "attributes")
            ET.SubElement(attrs, "staff-details", {"print-object": "no"})

        upper_mr = ET.SubElement(measure, "note", {"print-object": "no"})
        ET.SubElement(upper_mr, "rest", {"measure": "yes"})
        ET.SubElement(upper_mr, "duration").text = MEASURE_REST_DURATION
        ET.SubElement(upper_mr, "voice").text = "1"
        ET.SubElement(upper_mr, "staff").text = "1"

        if is_grand_staff:
            backup = ET.SubElement(measure, "backup")
            ET.SubElement(backup, "duration").text = MEASURE_REST_DURATION

            lower_mr = ET.SubElement(measure, "note", {"print-object": "no"})
            ET.SubElement(lower_mr, "rest", {"measure": "yes"})
            ET.SubElement(lower_mr, "duration").text = MEASURE_REST_DURATION
            ET.SubElement(lower_mr, "voice").text = "5"
            ET.SubElement(lower_mr, "staff").text = "2"

    return part
