"""Storage tests against a real MinIO — the one from the local dev stack.

Skipped entirely when MinIO is not reachable, so the ordinary `pytest` run stays
hermetic; run `docker compose up` in `/deploy` to exercise these.

They are worth running against the real thing rather than a fake because what
they check is the *rooting*: a key is built with the deployment's prefix and the
page ID on the front, and a listing has to take both back off. Getting that
wrong does not raise — it reads nothing and writes where nobody looks.
"""

import socket

import pytest

from musibot.orchestrator_head.config import OrchestratorHeadSettings
from musibot.orchestrator_head.storage import FileNotInPage, PageStorage

TEST_BUCKET = "musibot-test"

PAGE = "7Kf2mP9xLwQa"
OTHER_PAGE = "pageBBBBBBBB"


def minio_is_up() -> bool:
    try:
        with socket.create_connection(("localhost", 9000), timeout=0.5):
            return True
    except OSError:
        return False


pytestmark = pytest.mark.skipif(not minio_is_up(), reason="MinIO is not running")


@pytest.fixture(params=["", "s3/"], ids=["unrooted", "rooted"])
def storage(request: pytest.FixtureRequest) -> PageStorage:
    """Storage under both rootings, because production runs the second one."""
    settings = OrchestratorHeadSettings.for_testing(
        s3_bucket=TEST_BUCKET, s3_key_prefix=request.param
    )
    store = PageStorage(settings)

    # A dedicated bucket, so the test never disturbs real page data.
    client = store._client
    try:
        client.create_bucket(Bucket=TEST_BUCKET)
    except client.exceptions.BucketAlreadyOwnedByYou:
        pass

    # Everything, not just this rooting's prefix — otherwise the two
    # parametrisations leave objects lying in wait for each other.
    listing = client.list_objects_v2(Bucket=TEST_BUCKET)
    for entry in listing.get("Contents", []):
        client.delete_object(Bucket=TEST_BUCKET, Key=entry["Key"])

    return store


def test_a_write_then_a_read_round_trips(storage: PageStorage) -> None:
    storage.write(PAGE, "image.jpg", b"hello bytes")

    assert storage.read(PAGE, "image.jpg") == b"hello bytes"


def test_a_write_replaces_what_was_there(storage: PageStorage) -> None:
    # How a Pipeline overwrites a File an earlier execution produced.
    storage.write(PAGE, "layout.json", b"first")
    storage.write(PAGE, "layout.json", b"second")

    assert storage.read(PAGE, "layout.json") == b"second"


def test_reading_a_file_that_is_not_there_says_which(storage: PageStorage) -> None:
    with pytest.raises(FileNotInPage) as failure:
        storage.read(PAGE, "layout.json")

    assert "layout.json" in str(failure.value)


def test_listing_names_files_as_a_signature_would(storage: PageStorage) -> None:
    """The paths that come back have to be the ones a *Signature* is written in.

    Both the deployment's key prefix and the page ID go on when a key is built,
    and both have to come back off here.
    """
    storage.write(PAGE, "image.jpg", b"12345")
    storage.write(PAGE, "Staves/1/image.jpg", b"678")
    storage.write(OTHER_PAGE, "image.jpg", b"b")

    assert storage.list_files(PAGE) == ["Staves/1/image.jpg", "image.jpg"]


def test_listing_an_empty_page_finds_nothing(storage: PageStorage) -> None:
    assert storage.list_files(PAGE) == []


def test_existence_is_answered_either_way(storage: PageStorage) -> None:
    storage.write(PAGE, "image.jpg", b"a")

    assert storage.exists(PAGE, "image.jpg") is True
    assert storage.exists(PAGE, "layout.json") is False
    assert storage.exists(OTHER_PAGE, "image.jpg") is False


def test_the_rooting_is_where_the_object_actually_lands(storage: PageStorage) -> None:
    """Everything else here would pass just as well if the prefix were applied
    consistently but wrongly; this reads the raw listing to say where the bytes
    went — and it is the same place the `api` service and a *Worker Head* look."""
    storage.write(PAGE, "image.jpg", b"a")

    listing = storage._client.list_objects_v2(Bucket=TEST_BUCKET)
    keys = [entry["Key"] for entry in listing.get("Contents", [])]

    assert keys == [storage._layout.prefix() + f"{PAGE}/image.jpg"]
