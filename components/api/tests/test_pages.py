from fastapi.testclient import TestClient
from musibot.core import validate_page_id


def test_health_needs_no_auth(client: TestClient) -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_create_a_page(client: TestClient, alice: dict[str, str]) -> None:
    response = client.post("/musicorpus-pages", headers=alice)

    assert response.status_code == 201
    body = response.json()
    assert validate_page_id(body["page_id"]) == body["page_id"]
    assert body["executions"] == []


def test_created_pages_get_distinct_ids(client: TestClient, alice: dict[str, str]) -> None:
    ids = {client.post("/musicorpus-pages", headers=alice).json()["page_id"] for _ in range(20)}

    assert len(ids) == 20


def test_fetch_a_page(client: TestClient, alice: dict[str, str]) -> None:
    page_id = client.post("/musicorpus-pages", headers=alice).json()["page_id"]

    response = client.get(f"/musicorpus-pages/{page_id}", headers=alice)

    assert response.status_code == 200
    assert response.json()["page_id"] == page_id


def test_delete_a_page(client: TestClient, alice: dict[str, str]) -> None:
    page_id = client.post("/musicorpus-pages", headers=alice).json()["page_id"]

    response = client.delete(f"/musicorpus-pages/{page_id}", headers=alice)
    assert response.status_code == 204

    assert client.get(f"/musicorpus-pages/{page_id}", headers=alice).status_code == 404


# --- Authentication ----------------------------------------------------------


def test_a_request_without_a_token_is_rejected(client: TestClient) -> None:
    response = client.post("/musicorpus-pages")

    assert response.status_code == 401
    assert response.headers["WWW-Authenticate"] == "Bearer"


def test_a_request_with_an_unknown_token_is_rejected(client: TestClient) -> None:
    response = client.post("/musicorpus-pages", headers={"Authorization": "Bearer nope"})

    assert response.status_code == 401


def test_a_non_bearer_authorization_is_rejected(client: TestClient) -> None:
    response = client.post("/musicorpus-pages", headers={"Authorization": "Basic YWxpY2U6cA=="})

    assert response.status_code == 401


# --- Ownership ---------------------------------------------------------------


def test_a_user_cannot_fetch_another_users_page(
    client: TestClient, alice: dict[str, str], bob: dict[str, str]
) -> None:
    page_id = client.post("/musicorpus-pages", headers=alice).json()["page_id"]

    # Bob gets 404, not 403 — he must not learn the page exists at all.
    assert client.get(f"/musicorpus-pages/{page_id}", headers=bob).status_code == 404


def test_a_user_cannot_delete_another_users_page(
    client: TestClient, alice: dict[str, str], bob: dict[str, str]
) -> None:
    page_id = client.post("/musicorpus-pages", headers=alice).json()["page_id"]

    assert client.delete(f"/musicorpus-pages/{page_id}", headers=bob).status_code == 404
    # ... and Alice's page is untouched.
    assert client.get(f"/musicorpus-pages/{page_id}", headers=alice).status_code == 200


def test_a_missing_page_is_404(client: TestClient, alice: dict[str, str]) -> None:
    assert client.get("/musicorpus-pages/aaaaaaaaaaaa", headers=alice).status_code == 404
