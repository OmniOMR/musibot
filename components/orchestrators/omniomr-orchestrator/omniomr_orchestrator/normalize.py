from dataclasses import dataclass, fields
from xml.etree import ElementTree as ET
from musibot.orchestrator_head import PipelineContext
import traceback
from contextlib import contextmanager

from lmx.musicxml.omitted_staff_header.normalize_invisible_header_clef import (
    normalize_invisible_header_clef,
)
from lmx.musicxml.omitted_staff_header.normalize_invisible_key_signature import (
    normalize_invisible_key_signature,
)
from lmx.musicxml.omitted_staff_header.normalize_invisible_time_signature import (
    normalize_invisible_time_signature,
)
from lmx.musicxml.pitch.Clef import Clef, G_CLEF, F_CLEF


def _upper_staff_default_clef(*, print_object: bool) -> ET.Element:
    """
    Project-agreed default clef for a single staff
    instrument or for an upper staff of a grand staff.

    G clef at line 2.
    """
    clef_attrs = {"number": "1"}
    if print_object is False:
        clef_attrs["print-object"] = "no"
    clef = ET.Element("clef", clef_attrs)
    ET.SubElement(clef, "sign").text = "G"
    ET.SubElement(clef, "line").text = "2"
    return clef


def _lower_staff_default_clef(*, print_object: bool) -> ET.Element:
    """
    Project-agreed default clef
    for a lower staff of a grand staff.

    F clef at line 4.
    """
    clef_attrs = {"number": "2"}
    if print_object is False:
        clef_attrs["print-object"] = "no"
    clef = ET.Element("clef", clef_attrs)
    ET.SubElement(clef, "sign").text = "F"
    ET.SubElement(clef, "line").text = "4"
    return clef


def _normalize_key_numbers(part: ET.Element) -> ET.Element:
    """
    Remove "number" attributes from the first `<key>` element
    inside a part. The second `<key>` is removed entirely.
    """
    for attributes in part.findall(".//measure/attributes"):
        for key in attributes.findall("key"):
            number = key.attrib.get("number")
            # This key is extra
            if number == "2":
                attributes.remove(key)
            elif number is not None:
                del key.attrib["number"]

    return part


@contextmanager
def _normalization_step(ctx: PipelineContext, step_name: str):
    """
    Runs one normalization step, catching `ValueError`/`AssertionError` and
    logging them instead of failing the whole part. The step name is
    included in the log message.
    """
    try:
        yield
    except (ValueError, AssertionError):
        ctx.logger.info(f"Normalization step {step_name} failed:")
        ctx.logger.info(traceback.format_exc())


@dataclass
class NormalizationState:
    upper_clef: Clef = G_CLEF
    lower_clef: Clef = F_CLEF
    time_signature: ET.Element | None = None
    key_signature: int = 0

    def __str__(self) -> str:
        parts = [f"{field.name}={self._format_field(field.name)}" for field in fields(self)]
        return f"{type(self).__name__}({', '.join(parts)})"

    def _format_field(self, name: str) -> str:
        value = getattr(self, name)
        if name == "time_signature":
            return self._format_time_signature(value)
        return str(value)

    @staticmethod
    def _format_time_signature(value: ET.Element | None) -> str:
        if value is None:
            return "None"
        return f"{value.findtext('beats')}/{value.findtext('beat-type')}"


class StaffNormalizer:
    def __init__(self) -> None:
        self._state = NormalizationState()

    def __str__(self) -> str:
        return str(self._state)

    def _part_has_visible_clef_at_start(self, part: ET.Element) -> bool:
        """
        True if a given part has a visible clef
        in the first measure with attributes.
        """
        attrs = part.find(".//measure/attributes")

        if attrs is None:
            return False

        for clef in part.findall(".//clef"):
            print_obj = clef.attrib.get("print-object")
            if print_obj is None or print_obj == "yes":
                return True
        return False

    def normalize_part_and_update_state(self, ctx: PipelineContext, part: ET.Element) -> ET.Element:
        """
        Normalizes clef, time signature and key signature
        of a single part based on the previously processed parts.
        """
        part = _normalize_key_numbers(part)
        part = self._normalize_part(ctx, part)
        self._update_state(part)
        return part

    def _normalize_part(self, ctx: PipelineContext, part: ET.Element) -> ET.Element:
        with _normalization_step(ctx, "clef"):
            part = normalize_invisible_header_clef(
                part,
                desired_clef=[self._state.upper_clef, self._state.lower_clef],
                when_clef_visible="dont-normalize",
            )
        with _normalization_step(ctx, "time signature"):
            part = normalize_invisible_time_signature(
                part,
                desired_time=self._state.time_signature,
                when_time_visible="dont-normalize",
            )
        # normalize key only if a visible clef at the start is missing
        if not self._part_has_visible_clef_at_start(part):
            with _normalization_step(ctx, "key signature"):
                part = normalize_invisible_key_signature(
                    part,
                    desired_key=self._state.key_signature,
                    when_key_visible="dont-normalize",
                )

        return part

    def _update_state(self, part: ET.Element) -> None:
        # find last clefs, time and key
        upper_clef, lower_clef = self._find_last_clefs(part)
        key = self._find_last_key_signature(part)
        time = self._find_last_time_signature(part)

        # update
        if upper_clef is not None:
            self._state.upper_clef = upper_clef
        if lower_clef is not None:
            self._state.lower_clef = lower_clef

        self._state.time_signature = time
        if key is not None:
            self._state.key_signature = key

    def _find_last_clefs(self, part: ET.Element) -> tuple[Clef | None, Clef | None]:
        # TODO:
        # This search is partially incorrect, the last clef
        # when reading the XML does not have to be the clef
        # with the greatest onset. Although, it is very
        # improbable that Zeus would output something like this.
        clefs: dict[int, Clef | None] = {1: None, 2: None}

        for clef_e in part.findall(".//clef"):
            clef = Clef.from_clef_element(clef_e)
            staff_number = int(clef_e.attrib.get("number", "1"))
            clefs[staff_number] = clef

        return clefs[1], clefs[2]

    def _find_last_key_signature(self, part: ET.Element) -> int | None:
        key = None

        for key_e in part.findall(".//key"):
            fifths = key_e.find("fifths")
            if fifths is None or fifths.text is None:
                key = 0
            else:
                key = int(fifths.text)

        return key

    def _find_last_time_signature(self, part: ET.Element) -> ET.Element | None:
        _time = None
        for _time_e in part.findall(".//time"):
            _time = _time_e
        return _time
