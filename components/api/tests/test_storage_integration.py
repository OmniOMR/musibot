"""Storage tests against a real MinIO — the one from the local dev stack.

Skipped entirely when MinIO is not reachable, so the ordinary `pytest` run
stays hermetic; run `docker compose up` in `/deploy` to exercise these.
"""

import socket

import httpx
import pytest

from musibot.api.config import ApiSettings
from musibot.api.storage import Storage

TEST_BUCKET = "musibot-test"


def minio_is_up() -> bool:
    try:
        with socket.create_connection(("localhost", 9000), timeout=0.5):
            return True
    except OSError:
        return False


pytestmark = pytest.mark.skipif(not minio_is_up(), reason="MinIO is not running")


@pytest.fixture(params=["", "s3/"], ids=["unrooted", "rooted"])
def storage(request: pytest.FixtureRequest) -> Storage:
    """Storage under both rootings, because production runs the second one.

    A deployment served from a path prefix keeps its pages under a key prefix
    (see `ObjectLayout`), and every behaviour below — presigning, deleting a
    page, measuring the quota, wiping at startup — reads or writes keys. Each
    one is a place where the rooting could be applied on the way in and
    forgotten on the way out, which fails by finding nothing rather than by
    raising.
    """
    settings = ApiSettings.for_testing(
        s3_bucket=TEST_BUCKET,
        s3_key_prefix=request.param,
        # Redeemed against MinIO itself rather than through the nginx the
        # service is normally published behind, which is what the default
        # public URL points at. A signature covers the host it was made for, so
        # this has to be the address these tests actually fetch from.
        s3_public_url=None,
    )
    store = Storage(settings)
    # A dedicated bucket, so the test never disturbs real page data.
    client = store._client
    try:
        client.create_bucket(Bucket=TEST_BUCKET)
    except client.exceptions.BucketAlreadyOwnedByYou:
        pass
    # Everything, not just this rooting's prefix — otherwise the two
    # parametrisations leave objects lying in wait for each other.
    store._delete_prefix("")
    return store


def test_a_presigned_put_then_get_round_trips(storage: Storage) -> None:
    put_url = storage.presign("7Kf2mP9xLwQa", "image.jpg", "put", 300)
    assert httpx.put(put_url, content=b"hello bytes").status_code == 200

    get_url = storage.presign("7Kf2mP9xLwQa", "image.jpg", "get", 300)
    response = httpx.get(get_url)

    assert response.status_code == 200
    assert response.content == b"hello bytes"


def test_deleting_a_page_removes_only_its_files(storage: Storage) -> None:
    httpx.put(storage.presign("pageAAAAAAAA", "image.jpg", "put", 300), content=b"a")
    httpx.put(storage.presign("pageBBBBBBBB", "image.jpg", "put", 300), content=b"b")

    storage.delete_page("pageAAAAAAAA")

    assert httpx.get(storage.presign("pageAAAAAAAA", "image.jpg", "get", 300)).status_code == 404
    assert httpx.get(storage.presign("pageBBBBBBBB", "image.jpg", "get", 300)).status_code == 200


def test_listing_a_page_names_files_as_a_signature_would(storage: Storage) -> None:
    """The paths that come back have to be the ones a *Signature* is written in.

    Both the deployment's key prefix and the page ID go on when a key is built,
    and both have to come back off here. Leaving either on fails quietly: every
    path would still look plausible and none of them would match a *File* the
    *User* asked to be processed.
    """
    httpx.put(storage.presign("pageAAAAAAAA", "image.jpg", "put", 300), content=b"12345")
    httpx.put(storage.presign("pageAAAAAAAA", "Staves/1/image.jpg", "put", 300), content=b"678")
    httpx.put(storage.presign("pageBBBBBBBB", "image.jpg", "put", 300), content=b"b")

    files = storage.list_page_files("pageAAAAAAAA")

    assert [(file.path, file.size) for file in files] == [
        ("Staves/1/image.jpg", 3),
        ("image.jpg", 5),
    ]


def test_listing_an_empty_page_finds_nothing(storage: Storage) -> None:
    assert storage.list_page_files("pageAAAAAAAA") == []


def test_listing_sees_a_file_that_was_overwritten(storage: Storage) -> None:
    """Why the answer is asked of storage every time rather than remembered.

    A second *Pipeline Execution* may rewrite a *File* the first one produced,
    and a listing reports what is there now — the new size, and a timestamp that
    moved — where a remembered list would report the first execution's.
    """
    httpx.put(storage.presign("pageAAAAAAAA", "layout.json", "put", 300), content=b"first")
    before = storage.list_page_files("pageAAAAAAAA")[0]

    httpx.put(storage.presign("pageAAAAAAAA", "layout.json", "put", 300), content=b"second write")
    after = storage.list_page_files("pageAAAAAAAA")[0]

    assert (before.size, after.size) == (5, 12)
    assert after.last_modified >= before.last_modified


def test_page_sizes_totals_each_page_folder(storage: Storage) -> None:
    """What the public storage quota is read against.

    Worth exercising against a real MinIO rather than a fake: the sizes come
    from parsing object keys back into page IDs, and only a real listing proves
    that nested paths are charged to the page they belong to rather than to a
    folder of their own.
    """
    httpx.put(storage.presign("pageAAAAAAAA", "image.jpg", "put", 300), content=b"12345")
    httpx.put(storage.presign("pageAAAAAAAA", "Staves/1/crop.jpg", "put", 300), content=b"678")
    httpx.put(storage.presign("pageBBBBBBBB", "image.jpg", "put", 300), content=b"b")

    assert storage.page_sizes() == {"pageAAAAAAAA": 8, "pageBBBBBBBB": 1}


def test_page_sizes_forgets_a_deleted_page(storage: Storage) -> None:
    httpx.put(storage.presign("pageAAAAAAAA", "image.jpg", "put", 300), content=b"12345")

    storage.delete_page("pageAAAAAAAA")

    assert storage.page_sizes() == {}


def test_wipe_empties_the_bucket(storage: Storage) -> None:
    httpx.put(storage.presign("pageAAAAAAAA", "image.jpg", "put", 300), content=b"a")

    storage.wipe_bucket()

    assert httpx.get(storage.presign("pageAAAAAAAA", "image.jpg", "get", 300)).status_code == 404


def test_the_rooting_is_where_the_object_actually_lands(storage: Storage) -> None:
    """The presigned URL and the stored key have to agree, and only MinIO knows.

    Everything else here would pass just as well if the prefix were applied
    consistently but wrongly; this reads the raw listing to say where the
    bytes went.
    """
    httpx.put(storage.presign("pageAAAAAAAA", "image.jpg", "put", 300), content=b"a")

    listing = storage._client.list_objects_v2(Bucket=TEST_BUCKET)
    keys = [entry["Key"] for entry in listing.get("Contents", [])]

    assert keys == [storage._layout.prefix() + "pageAAAAAAAA/image.jpg"]


def test_wiping_leaves_alone_what_is_not_ours(storage: Storage) -> None:
    """Why startup no longer empties the whole bucket.

    A deployment behind a path prefix has to name its bucket after that
    prefix's first segment, so the bucket is the deployment's, not this
    service's. Emptying all of it on startup would be reaching outside.
    """
    if not storage._layout.prefix():
        pytest.skip("with no rooting the bucket is entirely ours")

    storage._client.put_object(Bucket=TEST_BUCKET, Key="somebody-elses/thing.txt", Body=b"keep me")
    httpx.put(storage.presign("pageAAAAAAAA", "image.jpg", "put", 300), content=b"a")

    storage.wipe_bucket()

    survivors = [
        entry["Key"] for entry in storage._client.list_objects_v2(Bucket=TEST_BUCKET)["Contents"]
    ]
    assert survivors == ["somebody-elses/thing.txt"]
