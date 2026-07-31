"""The OpenAPI document, which is what the interactive docs at `/docs` are built
from — so these are really tests that the API can be driven from a browser."""

from typing import Any

from fastapi.testclient import TestClient


def spec(client: TestClient) -> dict[str, Any]:
    document: dict[str, Any] = client.get("/openapi.json").json()
    return document


def test_the_api_token_is_one_security_scheme_not_a_header_on_every_endpoint(
    client: TestClient,
) -> None:
    """What gives `/docs` its **Authorize** button.

    Spelled as a header parameter it was a field to retype on every request,
    which is both tedious and easy to get subtly wrong.
    """
    schemes = spec(client)["components"]["securitySchemes"]

    assert schemes == {
        "API token": {
            "type": "http",
            "scheme": "bearer",
            "description": (
                "The API token issued to you, sent as `Authorization: Bearer <token>`."
            ),
        }
    }


def test_no_endpoint_asks_for_the_authorization_header_by_hand(client: TestClient) -> None:
    for path, operations in spec(client)["paths"].items():
        for method, operation in operations.items():
            header_parameters = [
                parameter["name"]
                for parameter in operation.get("parameters", [])
                if parameter["in"] == "header"
            ]
            assert header_parameters == [], f"{method.upper()} {path}"


def test_every_authenticated_endpoint_requires_the_scheme(client: TestClient) -> None:
    paths = spec(client)["paths"]

    # The only two endpoints that may be reached without a token: a liveness
    # check nothing may gate, and the endpoint a token is obtained from.
    open_paths = {"/health", "/public-sessions"}

    for path, operations in paths.items():
        if path in open_paths:
            continue
        for method, operation in operations.items():
            assert operation.get("security") == [{"API token": []}], f"{method.upper()} {path}"

    for path in open_paths:
        for operation in paths[path].values():
            assert "security" not in operation, path


def test_the_three_ways_of_getting_a_token_wrong_are_told_apart(client: TestClient) -> None:
    missing = client.post("/musicorpus-pages")
    not_bearer = client.post("/musicorpus-pages", headers={"Authorization": "Basic YWxpY2U6cA=="})
    unknown = client.post("/musicorpus-pages", headers={"Authorization": "Bearer nope"})

    assert missing.json()["detail"] == "Missing Authorization header"
    assert not_bearer.json()["detail"] == "Authorization header must be 'Bearer <token>'"
    assert unknown.json()["detail"] == "Unknown API token"

    for response in (missing, not_bearer, unknown):
        assert response.status_code == 401
        assert response.headers["WWW-Authenticate"] == "Bearer"
