"""*Musicorpus Pages*: their identity, their file paths, and where they are stored.

Musibot treats a *MusicorpusPage* as a folder of *Files* and a *File* as opaque
bytes. What is inside a file, and which files mean what, is governed by the
Musicorpus Specification and is the business of the *Models* and *Pipelines*
that read and write them — not of Musibot, which only moves them around.

So this module is deliberately small: it says what a page ID looks like, what a
file path within a page may look like, and how the two map onto object storage
and onto the local mirror a *Worker Head* hands to its *Model*.
"""

from pathlib import Path, PurePosixPath
from typing import Annotated

from pydantic import AfterValidator

from musibot.core.identifiers import ID_ALPHABET, ID_LENGTH, is_well_formed_id, random_id

PAGE_ID_LENGTH = ID_LENGTH
PAGE_ID_ALPHABET = ID_ALPHABET

# An object key in S3 may be 1024 bytes; the page ID and a separator take some
# of that, so a file path within a page gets the rest, rounded down.
MAX_FILE_PATH_LENGTH = 1000


class InvalidPageId(ValueError):
    """Raised for a page ID that Musibot would never have issued."""


class InvalidFilePath(ValueError):
    """Raised for a file path that is not safely contained within its page."""


def generate_page_id() -> str:
    """Make up a new page ID.

    IDs are random rather than sequential so that pages cannot be enumerated
    across *Users* — defense in depth behind the ownership check in the `api`
    service.
    """
    return random_id()


def validate_page_id(page_id: str) -> str:
    """Return the page ID unchanged, or raise :class:`InvalidPageId`."""
    if not is_well_formed_id(page_id):
        raise InvalidPageId(f"A page ID is {PAGE_ID_LENGTH} alphanumeric characters: {page_id!r}")

    return page_id


def validate_file_path(file_path: str) -> str:
    """Return the file path unchanged, or raise :class:`InvalidFilePath`.

    A valid path is relative, uses `/` as its only separator, and names a file
    inside its own *MusicorpusPage* — `Staves/1/image.jpg` and the like.

    Note that this validates rather than sanitizes. A path that is not already
    safe is rejected, never repaired: rewriting `../../etc/passwd` into
    something harmless would answer a request nobody made, and would hide the
    bug (or the attack) that produced it.
    """
    if not file_path:
        raise InvalidFilePath("A file path may not be empty")

    if len(file_path) > MAX_FILE_PATH_LENGTH:
        raise InvalidFilePath(
            f"A file path may be at most {MAX_FILE_PATH_LENGTH} characters: {file_path[:40]!r}..."
        )

    if "\\" in file_path:
        # Not a separator here, and allowing it would mean two spellings of the
        # same path — one of which the checks below would not see through.
        raise InvalidFilePath(f"A file path separator is `/`, not `\\`: {file_path!r}")

    if any(character in file_path for character in ("\x00", "\n", "\r")) or any(
        ord(character) < 0x20 or ord(character) == 0x7F for character in file_path
    ):
        raise InvalidFilePath(f"A file path may not contain control characters: {file_path!r}")

    if file_path.startswith("/"):
        raise InvalidFilePath(f"A file path is relative to its page: {file_path!r}")

    segments = file_path.split("/")

    if "" in segments:
        # Catches `a//b`, and a trailing `/` — which would name a folder.
        raise InvalidFilePath(f"A file path may not have empty segments: {file_path!r}")

    if "." in segments or ".." in segments:
        raise InvalidFilePath(f"A file path may not navigate with `.` or `..`: {file_path!r}")

    if any(segment.strip() == "" for segment in segments):
        raise InvalidFilePath(f"A file path may not have blank segments: {file_path!r}")

    return file_path


PageId = Annotated[str, AfterValidator(validate_page_id)]
"""A page ID, validated wherever it appears in a message or a request."""

PageFilePath = Annotated[str, AfterValidator(validate_file_path)]
"""A file path within a page, validated wherever it appears."""


def object_prefix(page_id: str) -> str:
    """The object storage prefix under which a whole page lives.

    Every page is a top-level folder in the one global bucket.
    """
    return validate_page_id(page_id) + "/"


def object_key(page_id: str, file_path: str) -> str:
    """The object storage key of one *File* of one page."""
    return object_prefix(page_id) + validate_file_path(file_path)


def local_path(pages_dir: Path, page_id: str, file_path: str) -> Path:
    """Where one *File* of one page sits in a local mirror of the storage.

    This is the mirror a *Worker Head* stages for its *Model* (see
    `docs/worker-ipc.md`), and the path is checked to fall inside the page's own
    folder even after symbolic links are resolved — a *Model* is free to create
    those, and a validated path alone does not account for them.
    """
    page_dir = pages_dir / validate_page_id(page_id)
    resolved = (page_dir / PurePosixPath(validate_file_path(file_path))).resolve()

    if not resolved.is_relative_to(page_dir.resolve()):
        raise InvalidFilePath(
            f"File path escapes its page folder once resolved: {file_path!r} in {page_id!r}"
        )

    return resolved
