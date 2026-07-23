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
