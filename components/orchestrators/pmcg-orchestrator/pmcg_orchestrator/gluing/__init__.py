"""Gluing staff transcriptions into one page-level MusicXML file.

Each version of the gluing is a module of its own — `v1` is what `mzk-page` `1`
does and `v2` what `mzk-page` `2` does — because the version a *User* pins is the behaviour they get, and a newer
gluing is published beside an older one rather than in place of it.

Like the slicing, this is *Musicorpus* logic rather than *Musibot* logic and
will move to a library of its own when there is one.
"""

from dataclasses import dataclass


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
