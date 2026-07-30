"""*File patterns*: what a *Signature* says, and whether an input list fits it.

A *Signature* does not name *Files*. It describes which sets of *Files* are
admissible, so that the *Pipeline* listing can tell a *User* what to send —
`Staves/{s}/image.jpg` rather than a `Staves/7/image.jpg` that would be true of
one page and wrong for the next. See `docs/signatures.md`.

A pattern is an ordinary page-relative path in which a whole segment may be a
**slot**: `{}` and `{name}` stand for one subdivision instance, `{*}` and
`{*name}` for all of them, and a repeated name binds two slots to the same
instance or the same set. Braces rather than a bare `*` are deliberate — they
say *slot* and stop short of inviting `*.jpg` and `**`, which would mean owning
a glob engine.

Nothing here knows that the segment before a slot is called `Staves`. A future
subdivision level should not be a change to Musibot, for the same reason a new
file format is not one.
"""

import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Annotated

from pydantic import AfterValidator

from musibot.core.page import MAX_FILE_PATH_LENGTH, InvalidFilePath, validate_file_path


class InvalidFilePattern(ValueError):
    """Raised for a pattern that is not one a *Signature* may contain."""


class SignatureMismatch(ValueError):
    """Raised when a list of *Files* does not fit a *Signature's* patterns.

    Carries a message written for whoever sent the list, since it comes back to
    them as the body of a `400`.
    """


_SLOT = re.compile(r"^\{(\*?)([A-Za-z0-9_-]*)\}$")

_SKELETON_SEGMENT = "_"
"""Stands in for a slot while the surrounding path is checked by
`musibot.core.page`, so that the two do not have to agree about what a path
segment may contain by each spelling out the rules."""


@dataclass(frozen=True)
class Slot:
    """One subdivision instance, or all of them."""

    name: str | None
    many: bool


@dataclass(frozen=True)
class FilePattern:
    """One entry of a *Signature*, parsed."""

    text: str
    """As written, `?` included — what a listing shows and an error quotes."""

    segments: tuple[str | Slot, ...]
    optional: bool

    @property
    def is_concrete(self) -> bool:
        """Whether this names one *File* outright, with no slots in it."""
        return all(isinstance(segment, str) for segment in self.segments)

    @property
    def accepts_many(self) -> bool:
        """Whether one execution may bring any number of *Files* for this entry."""
        return any(isinstance(segment, Slot) and segment.many for segment in self.segments)

    @property
    def concrete_path(self) -> str:
        """The one *File* this names. Only meaningful when `is_concrete`."""
        return "/".join(segment for segment in self.segments if isinstance(segment, str))

    def match(self, file_path: str) -> bool:
        """Whether a concrete path is one this entry describes."""
        segments = file_path.split("/")
        if len(segments) != len(self.segments):
            return False
        return all(
            isinstance(expected, Slot) or expected == actual
            for expected, actual in zip(self.segments, segments)
        )


def parse_file_pattern(pattern: str) -> FilePattern:
    """Parse one *Signature* entry, or raise :class:`InvalidFilePattern`."""
    if not pattern:
        raise InvalidFilePattern("A file pattern may not be empty")

    if len(pattern) > MAX_FILE_PATH_LENGTH:
        raise InvalidFilePattern(
            f"A file pattern may be at most {MAX_FILE_PATH_LENGTH} characters: {pattern[:40]!r}..."
        )

    optional = pattern.endswith("?")
    body = pattern[:-1] if optional else pattern

    segments: list[str | Slot] = []
    skeleton: list[str] = []
    for segment in body.split("/"):
        slot = _parse_slot(segment, pattern)
        segments.append(segment if slot is None else slot)
        skeleton.append(segment if slot is None else _SKELETON_SEGMENT)

    # Everything a path must be — relative, `/`-separated, free of `..` and of
    # control characters — a pattern must be too, so the one implementation of
    # those rules is asked rather than repeated. Braces are refused there, which
    # is what leaves them free to mean "slot" here.
    try:
        validate_file_path("/".join(skeleton))
    except InvalidFilePath as error:
        raise InvalidFilePattern(f"Not a valid file pattern: {pattern!r} ({error})") from error

    return FilePattern(text=pattern, segments=tuple(segments), optional=optional)


def validate_file_pattern(pattern: str) -> str:
    """Return the pattern unchanged, or raise :class:`InvalidFilePattern`."""
    parse_file_pattern(pattern)
    return pattern


PageFilePattern = Annotated[str, AfterValidator(validate_file_pattern)]
"""One entry of a *Signature*, validated wherever it appears in a message."""


def parse_file_patterns(patterns: Iterable[str]) -> tuple[FilePattern, ...]:
    return tuple(parse_file_pattern(pattern) for pattern in patterns)


def check_slot_names(patterns: Iterable[FilePattern]) -> None:
    """Refuse a *Signature* whose slots disagree about what a name means.

    A name binds across the whole *Signature*, input and output together, so
    `{s}` in one entry and `{*s}` in another would be asking for one instance
    and every instance under the same name.
    """
    arity: dict[str, bool] = {}
    for pattern in patterns:
        for segment in pattern.segments:
            if not isinstance(segment, Slot) or segment.name is None:
                continue
            if arity.setdefault(segment.name, segment.many) != segment.many:
                raise InvalidFilePattern(
                    f"The slot name {segment.name!r} is used as both {{{segment.name}}} and "
                    f"{{*{segment.name}}}; a name means one instance or every instance, "
                    f"not both"
                )


def check_input_files(patterns: Sequence[FilePattern], file_paths: Sequence[str]) -> None:
    """Raise :class:`SignatureMismatch` unless this input list fits these patterns.

    This is string matching and nothing more — it never looks at a *Musicorpus
    Page*, and it is not the same thing as expanding a pattern into paths, which
    would need the page's contents.
    """
    _check_no_duplicates(file_paths)

    matches: list[list[str]] = [[] for _ in patterns]
    for file_path in file_paths:
        hit = False
        for index, pattern in enumerate(patterns):
            if pattern.match(file_path):
                matches[index].append(file_path)
                hit = True
        if not hit:
            raise SignatureMismatch(
                f"The input file {file_path!r} is not named by the signature ({_spell(patterns)})"
            )

    bindings: dict[str, list[tuple[str, frozenset[str]]]] = {}
    for pattern, matched in zip(patterns, matches):
        _check_arity(pattern, matched)
        for name, values in _named_slot_values(pattern, matched).items():
            bindings.setdefault(name, []).append((pattern.text, values))

    _check_bindings_agree(bindings)


def concrete_outputs(patterns: Iterable[FilePattern]) -> list[str]:
    """The *Files* a *Signature* promises outright.

    Only the slot-free, non-optional entries: everything else is a promise about
    a shape, and how many *Files* fill it is the *Model's* to decide.
    """
    return [
        pattern.concrete_path
        for pattern in patterns
        if pattern.is_concrete and not pattern.optional
    ]


# --- internals ---------------------------------------------------------------


def _parse_slot(segment: str, pattern: str) -> Slot | None:
    """Read one path segment as a slot, or as a literal if it holds no braces."""
    if "{" not in segment and "}" not in segment:
        return None

    match = _SLOT.match(segment)
    if match is None:
        # Most often `image.{v}.jpg`. A slot occupies a whole segment, so that
        # matching stays a segment-by-segment comparison and never a search
        # within a name.
        raise InvalidFilePattern(
            f"A slot is a whole path segment, written {{}}, {{name}}, {{*}} or {{*name}}: "
            f"{segment!r} in {pattern!r}"
        )

    return Slot(name=match.group(2) or None, many=match.group(1) == "*")


def _check_no_duplicates(file_paths: Sequence[str]) -> None:
    seen: set[str] = set()
    for file_path in file_paths:
        if file_path in seen:
            raise SignatureMismatch(f"The input file {file_path!r} is named twice")
        seen.add(file_path)


def _check_arity(pattern: FilePattern, matched: Sequence[str]) -> None:
    """Check how many *Files* arrived for one entry, and for each of its slots."""
    if not pattern.accepts_many:
        if not matched and not pattern.optional:
            raise SignatureMismatch(f"The input list names no {pattern.text!r}")
        if len(matched) > 1:
            raise SignatureMismatch(
                f"{pattern.text!r} names one file, but the input list has "
                f"{len(matched)}: {', '.join(repr(path) for path in matched)}"
            )

    # A `{}` slot sitting beside a `{*}` one in the same entry is unconstrained
    # by the count above, so it is checked on its own.
    for position, segment in enumerate(pattern.segments):
        if isinstance(segment, Slot) and not segment.many:
            values = {path.split("/")[position] for path in matched}
            if len(values) > 1:
                raise SignatureMismatch(
                    f"{pattern.text!r} names one instance, but the input list has "
                    f"{len(values)}: {', '.join(sorted(repr(value) for value in values))}"
                )


def _named_slot_values(pattern: FilePattern, matched: Sequence[str]) -> dict[str, frozenset[str]]:
    """What each named slot of one entry was bound to by the input list."""
    if not matched:
        # An optional entry nobody sent binds nothing, rather than binding its
        # names to the empty set and contradicting the entries that did arrive.
        return {}

    values: dict[str, frozenset[str]] = {}
    for position, segment in enumerate(pattern.segments):
        if isinstance(segment, Slot) and segment.name is not None:
            values[segment.name] = frozenset(path.split("/")[position] for path in matched)
    return values


def _check_bindings_agree(bindings: dict[str, list[tuple[str, frozenset[str]]]]) -> None:
    """Check that a name means the same instances everywhere it appears."""
    for name, occurrences in bindings.items():
        first_pattern, first_values = occurrences[0]
        for pattern_text, values in occurrences[1:]:
            if values != first_values:
                raise SignatureMismatch(
                    f"The slot {{{name}}} is bound to {_spell_values(first_values)} by "
                    f"{first_pattern!r} but to {_spell_values(values)} by {pattern_text!r}; "
                    f"a repeated slot name means the same instances throughout"
                )


def _spell(patterns: Iterable[FilePattern]) -> str:
    spelled = ", ".join(pattern.text for pattern in patterns)
    return spelled or "which names no input"


def _spell_values(values: frozenset[str]) -> str:
    return ", ".join(sorted(repr(value) for value in values)) or "nothing"
