from pathlib import Path

import pytest
from pydantic import BaseModel, ValidationError

from musibot.core.page import (
    MAX_FILE_PATH_LENGTH,
    PAGE_ID_LENGTH,
    InvalidFilePath,
    InvalidPageId,
    PageFilePath,
    PageId,
    generate_page_id,
    local_path,
    object_key,
    object_prefix,
    validate_file_path,
    validate_page_id,
)

VALID_PATHS = [
    "image.jpg",
    "transcription.musicxml",
    "Staves/1/image.jpg",
    "Staves/12/transcription.musicxml",
    "a.very.dotted.name.json",
    "name with spaces.jpg",
    "unicode-ěščřž.jpg",
    "...leading-dots.jpg",
    "deeply/nested/but/perfectly/fine/file.txt",
]

TRAVERSING_PATHS = [
    "../image.jpg",
    "..",
    "Staves/../../image.jpg",
    "Staves/1/../../../../etc/passwd",
    "./image.jpg",
    ".",
    "Staves/./image.jpg",
    "/etc/passwd",
    "/image.jpg",
    "//image.jpg",
    "Staves//image.jpg",
    "Staves/1/",
    "..\\image.jpg",
    "Staves\\1\\image.jpg",
    "image.jpg\x00.png",
    "image\n.jpg",
    "",
    " ",
    "Staves/ /image.jpg",
]


def test_generated_page_ids_are_valid_and_distinct() -> None:
    ids = {generate_page_id() for _ in range(1000)}

    assert len(ids) == 1000  # random, not sequential
    for page_id in ids:
        assert validate_page_id(page_id) == page_id
        assert len(page_id) == PAGE_ID_LENGTH


def test_page_ids_are_url_and_shell_safe() -> None:
    # No `-` or `_`: a page ID becomes a directory name, and one starting with
    # `-` is a nuisance to every command line tool that meets it.
    ids = "".join(generate_page_id() for _ in range(200))

    assert ids.isalnum()


@pytest.mark.parametrize(
    "page_id",
    ["", "short", "7Kf2mP9xLwQ", "7Kf2mP9xLwQxx", "7Kf2mP9xLw-Q", "7Kf2mP9xLw/Q", "../../../etc"],
)
def test_malformed_page_ids_are_refused(page_id: str) -> None:
    with pytest.raises(InvalidPageId):
        validate_page_id(page_id)


@pytest.mark.parametrize("file_path", VALID_PATHS)
def test_ordinary_file_paths_are_accepted(file_path: str) -> None:
    assert validate_file_path(file_path) == file_path


@pytest.mark.parametrize("file_path", TRAVERSING_PATHS)
def test_paths_that_could_escape_their_page_are_refused(file_path: str) -> None:
    with pytest.raises(InvalidFilePath):
        validate_file_path(file_path)


def test_an_over_long_path_is_refused() -> None:
    with pytest.raises(InvalidFilePath):
        validate_file_path("a" * (MAX_FILE_PATH_LENGTH + 1))


def test_a_valid_path_is_returned_unchanged_not_repaired() -> None:
    # Validation, not sanitization: a bad path is rejected rather than
    # rewritten into some other path the caller never asked for.
    assert validate_file_path("Staves/1/image.jpg") == "Staves/1/image.jpg"


def test_object_keys_place_each_page_in_its_own_folder() -> None:
    assert object_prefix("7Kf2mP9xLwQa") == "7Kf2mP9xLwQa/"
    assert object_key("7Kf2mP9xLwQa", "Staves/1/image.jpg") == "7Kf2mP9xLwQa/Staves/1/image.jpg"


def test_object_keys_validate_both_halves() -> None:
    with pytest.raises(InvalidPageId):
        object_key("../../secrets", "image.jpg")

    with pytest.raises(InvalidFilePath):
        object_key("7Kf2mP9xLwQa", "../other-page/image.jpg")


def test_local_paths_land_inside_the_page_folder(tmp_path: Path) -> None:
    path = local_path(tmp_path, "7Kf2mP9xLwQa", "Staves/1/image.jpg")

    assert path == tmp_path.resolve() / "7Kf2mP9xLwQa" / "Staves" / "1" / "image.jpg"


def test_local_paths_refuse_to_escape_the_page_folder(tmp_path: Path) -> None:
    with pytest.raises(InvalidFilePath):
        local_path(tmp_path, "7Kf2mP9xLwQa", "../7Kf2mP9xLwQb/image.jpg")


def test_local_paths_refuse_to_escape_through_a_symlink(tmp_path: Path) -> None:
    # A Model may create symlinks inside its own page folder; a path that is
    # valid as a string can still leave the folder once resolved.
    page_dir = tmp_path / "7Kf2mP9xLwQa"
    (page_dir / "Staves").mkdir(parents=True)
    (page_dir / "Staves" / "escape").symlink_to(tmp_path)

    with pytest.raises(InvalidFilePath):
        local_path(tmp_path, "7Kf2mP9xLwQa", "Staves/escape/other.jpg")


class Message(BaseModel):
    page: PageId
    file: PageFilePath


def test_the_annotated_types_validate_inside_a_message() -> None:
    message = Message(page="7Kf2mP9xLwQa", file="Staves/1/image.jpg")

    assert message.page == "7Kf2mP9xLwQa"
    assert message.file == "Staves/1/image.jpg"


@pytest.mark.parametrize(
    ("page", "file"),
    [("7Kf2mP9xLwQa", "../../etc/passwd"), ("../../etc", "image.jpg")],
)
def test_a_message_carrying_a_bad_path_fails_to_parse(page: str, file: str) -> None:
    # Validation rides along with the wire contract, so no consumer has to
    # remember to call it.
    with pytest.raises(ValidationError):
        Message(page=page, file=file)
