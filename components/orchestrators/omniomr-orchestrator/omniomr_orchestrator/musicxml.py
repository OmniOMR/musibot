"""Gluing staff transcriptions into one page-level MusicXML file.

Every staff's measures are appended to **one part**, in reading order, with an
explicit system break where each staff begins. The page then reads as what it
usually is — one instrument's music, laid out a system at a time — and the
staves keep the shape they were transcribed with, because a system break is a
layout instruction rather than a structural claim.

The obvious alternative, a part per staff, was tried first and is worse in the
common case. It reads a solo piece as an N-instrument score whose parts play
simultaneously, so nine staves of one melody become nine melodies at once. It
also needs every part to agree about how many measures there are, which staff
transcriptions of a real page never do.

What this still cannot express is genuine polyphony: a piano system's two
staves become two consecutive systems rather than one grand staff, and a
four-part system becomes four systems. Fixing that needs the layout's `system`
and `grandstaff` boxes, which the layout *Model* already reports and this does
not yet read. That is the next version of the pipeline.

Like the slicing, this is *Musicorpus* logic rather than *Musibot* logic and
will move to a library of its own when there is one.
"""

from dataclasses import dataclass
from xml.etree import ElementTree

MUSICXML_VERSION = "4.0"

PART_ID = "P1"
"""The one part. A page is one part now, whatever it has staves."""


class UnreadableTranscription(ValueError):
    """A staff transcription is not MusicXML this can take measures out of."""


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


def page_musicxml(staves: list[StaffTranscription]) -> str:
    """One `score-partwise` document holding every staff, one after another."""
    if not staves:
        raise UnreadableTranscription("A page needs at least one staff to be written")

    score = ElementTree.Element("score-partwise", {"version": MUSICXML_VERSION})

    part_list = ElementTree.SubElement(score, "part-list")
    score_part = ElementTree.SubElement(part_list, "score-part", {"id": PART_ID})
    part_name = ElementTree.SubElement(score_part, "part-name", {"print-object": "no"})
    part_name.text = "Music"

    part = ElementTree.SubElement(score, "part", {"id": PART_ID})

    number = 0
    for staff in staves:
        for position, measure in enumerate(_measures(staff, first_of_page=number == 0)):
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
                measure.insert(0, ElementTree.Element("print", {"new-system": "yes"}))

            part.append(measure)

    ElementTree.indent(score, space="  ")
    body = ElementTree.tostring(score, encoding="unicode")
    return f'<?xml version="1.0" encoding="UTF-8"?>\n{body}\n'


def _measures(staff: StaffTranscription, *, first_of_page: bool) -> list[ElementTree.Element]:
    """The measures one staff contributes to the page."""
    if staff.musicxml is None:
        return [_unreadable_measure(staff, first_of_page=first_of_page)]

    try:
        source = ElementTree.fromstring(staff.musicxml)
    except ElementTree.ParseError as error:
        raise UnreadableTranscription(
            f"The transcription of staff {staff.number} is not valid XML: {error}"
        )

    # Every measure of every part, in document order. A staff transcription is
    # one part, so this is that part's measures — and a model that produced more
    # than one has them concatenated rather than silently dropped.
    measures = source.findall(".//part/measure")

    if not measures:
        raise UnreadableTranscription(
            f"The transcription of staff {staff.number} contains no measures"
        )

    return measures


def _unreadable_measure(staff: StaffTranscription, *, first_of_page: bool) -> ElementTree.Element:
    """One measure standing in for a staff that has no transcription.

    It says so in the score itself, as a direction a renderer prints above the
    staff. An empty measure alone would be indistinguishable from a staff the
    *Model* read as silence, and telling a *User* that a page is silent where it
    was in fact unreadable is worse than telling them nothing.
    """
    measure = ElementTree.Element("measure", {"number": "0"})

    if first_of_page:
        # Only here. `divisions` is carried forward from measure to measure, so
        # restating it mid-page would rewrite what every following duration
        # means — while a part that opens without it has no scale at all.
        attributes = ElementTree.SubElement(measure, "attributes")
        divisions = ElementTree.SubElement(attributes, "divisions")
        divisions.text = "1"

    direction = ElementTree.SubElement(measure, "direction", {"placement": "above"})
    direction_type = ElementTree.SubElement(direction, "direction-type")
    words = ElementTree.SubElement(direction_type, "words")
    words.text = f"Staff {staff.number} could not be transcribed"

    note = ElementTree.SubElement(measure, "note")
    ElementTree.SubElement(note, "rest", {"measure": "yes"})
    duration = ElementTree.SubElement(note, "duration")
    # One division, whatever a division currently is: `measure="yes"` is what
    # carries the meaning, and any positive duration is valid under any scale.
    duration.text = "1"
    voice = ElementTree.SubElement(note, "voice")
    voice.text = "1"

    return measure
