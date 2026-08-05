from pathlib import Path

from fastapi.testclient import TestClient

from tests.fakes import FakeStorage


def make_page(client: TestClient, headers: dict[str, str]) -> str:
    return str(client.post("/musicorpus-pages", headers=headers).json()["page_id"])


def test_request_upload_and_download_urls(client: TestClient, alice: dict[str, str]) -> None:
    page_id = make_page(client, alice)

    response = client.post(
        f"/musicorpus-pages/{page_id}/file-urls",
        headers=alice,
        json={"put": ["image.jpg"], "get": ["transcription.musicxml"]},
    )

    assert response.status_code == 200
    body = response.json()
    assert "image.jpg" in body["put"]
    assert "transcription.musicxml" in body["get"]
    assert page_id in body["put"]["image.jpg"]
    assert "expires_at" in body


def test_an_empty_request_yields_empty_maps(client: TestClient, alice: dict[str, str]) -> None:
    page_id = make_page(client, alice)

    response = client.post(f"/musicorpus-pages/{page_id}/file-urls", headers=alice, json={})

    assert response.status_code == 200
    assert response.json()["put"] == {}
    assert response.json()["get"] == {}


def test_listing_a_fresh_page_finds_nothing(client: TestClient, alice: dict[str, str]) -> None:
    page_id = make_page(client, alice)

    response = client.get(f"/musicorpus-pages/{page_id}/files", headers=alice)

    assert response.status_code == 200
    assert response.json()["files"] == []


def test_listing_reports_what_storage_holds(
    client: TestClient, alice: dict[str, str], storage: FakeStorage
) -> None:
    page_id = make_page(client, alice)
    storage.put(page_id, "image.jpg", 4096)
    storage.put(page_id, "Staves/1/image.jpg", 512)

    response = client.get(f"/musicorpus-pages/{page_id}/files", headers=alice)

    files = response.json()["files"]
    assert [file["path"] for file in files] == ["Staves/1/image.jpg", "image.jpg"]
    assert [file["size"] for file in files] == [512, 4096]
    assert all("last_modified" in file for file in files)


def test_listing_shows_only_this_pages_files(
    client: TestClient, alice: dict[str, str], storage: FakeStorage
) -> None:
    """A page's folder is its own. The listing must not leak the neighbour's,
    which is the failure a prefix applied loosely would produce."""
    page_id = make_page(client, alice)
    other_page_id = make_page(client, alice)
    storage.put(page_id, "image.jpg", 1)
    storage.put(other_page_id, "transcription.musicxml", 2)

    response = client.get(f"/musicorpus-pages/{page_id}/files", headers=alice)

    assert [file["path"] for file in response.json()["files"]] == ["image.jpg"]


def test_listing_requires_ownership(
    client: TestClient, alice: dict[str, str], bob: dict[str, str], storage: FakeStorage
) -> None:
    page_id = make_page(client, alice)
    storage.put(page_id, "image.jpg", 1)

    response = client.get(f"/musicorpus-pages/{page_id}/files", headers=bob)

    assert response.status_code == 404


def test_listing_requires_auth(client: TestClient, alice: dict[str, str]) -> None:
    page_id = make_page(client, alice)

    response = client.get(f"/musicorpus-pages/{page_id}/files")

    assert response.status_code == 401


def test_a_traversing_path_is_rejected(client: TestClient, alice: dict[str, str]) -> None:
    page_id = make_page(client, alice)

    # 422: the path fails validation as the body is parsed, before any URL is
    # signed.
    response = client.post(
        f"/musicorpus-pages/{page_id}/file-urls",
        headers=alice,
        json={"get": ["../../etc/passwd"]},
    )

    assert response.status_code == 422


def test_file_urls_require_ownership(
    client: TestClient, alice: dict[str, str], bob: dict[str, str]
) -> None:
    page_id = make_page(client, alice)

    response = client.post(
        f"/musicorpus-pages/{page_id}/file-urls", headers=bob, json={"get": ["image.jpg"]}
    )

    assert response.status_code == 404


def test_file_urls_require_auth(client: TestClient, alice: dict[str, str]) -> None:
    page_id = make_page(client, alice)

    response = client.post(f"/musicorpus-pages/{page_id}/file-urls", json={"get": ["image.jpg"]})

    assert response.status_code == 401


def test_deleting_a_page_clears_its_storage(
    client: TestClient, alice: dict[str, str], storage: FakeStorage
) -> None:
    page_id = make_page(client, alice)

    client.delete(f"/musicorpus-pages/{page_id}", headers=alice)

    assert storage.deleted_pages == [page_id]


def test_file_urls_are_unavailable_without_storage(
    tokens_file: Path, alice: dict[str, str]
) -> None:
    from musibot.api.app import create_app
    from musibot.api.config import ApiSettings

    # A service running without object storage: the pages subset works, the
    # file endpoint reports it is unavailable rather than pretending.
    client = TestClient(create_app(ApiSettings.for_testing(api_tokens_file=tokens_file)))
    page_id = make_page(client, alice)

    response = client.post(
        f"/musicorpus-pages/{page_id}/file-urls", headers=alice, json={"get": ["image.jpg"]}
    )

    assert response.status_code == 503
    assert client.get(f"/musicorpus-pages/{page_id}/files", headers=alice).status_code == 503
