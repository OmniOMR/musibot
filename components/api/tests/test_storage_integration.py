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


@pytest.fixture
def storage() -> Storage:
    settings = ApiSettings.for_testing(s3_bucket=TEST_BUCKET)
    store = Storage(settings)
    # A dedicated bucket, so the test never disturbs real page data.
    client = store._client
    try:
        client.create_bucket(Bucket=TEST_BUCKET)
    except client.exceptions.BucketAlreadyOwnedByYou:
        pass
    store.wipe_bucket()
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
