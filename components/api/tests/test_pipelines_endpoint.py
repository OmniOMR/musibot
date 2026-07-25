"""`GET /pipelines` — the listing assembled from what was announced."""

from fastapi.testclient import TestClient

from musibot.api.discovery import ProviderRegistry
from tests.test_discovery import orchestrator_announcement, worker_announcement


def test_listing_requires_a_token(client: TestClient) -> None:
    assert client.get("/pipelines").status_code == 401


def test_an_empty_system_lists_nothing(client: TestClient, alice: dict[str, str]) -> None:
    response = client.get("/pipelines", headers=alice)

    assert response.status_code == 200
    assert response.json() == {"pipelines": [], "warnings": []}


def test_pipelines_and_implicit_pipelines_are_listed(
    client: TestClient, registry: ProviderRegistry, alice: dict[str, str]
) -> None:
    registry.record(orchestrator_announcement())
    registry.record(worker_announcement())

    body = client.get("/pipelines", headers=alice).json()

    assert body["warnings"] == []
    assert body["pipelines"] == [
        {
            "name": "hello-world",
            "version": "1.0.0",
            "signature": {"input": ["image.jpg"], "output": ["transcription.musicxml"]},
            "implicit": False,
            "orchestrators": ["reference-orchestrator"],
            "instances": 1,
        },
        {
            "name": "staff-detector",
            "version": "2026-07-22",
            "signature": {"input": ["image.jpg"], "output": ["layout.json"]},
            "implicit": True,
            "orchestrators": [],
            "instances": 1,
        },
    ]


def test_a_conflict_is_reported_alongside_the_listing(
    client: TestClient, registry: ProviderRegistry, alice: dict[str, str]
) -> None:
    registry.record(orchestrator_announcement(pipeline_name="staff-detector", version="2026-07-22"))
    registry.record(worker_announcement(model_name="staff-detector", version="2026-07-22"))

    body = client.get("/pipelines", headers=alice).json()

    assert len(body["pipelines"]) == 1
    assert body["warnings"] == [
        {
            "type": "name-collision",
            "message": body["warnings"][0]["message"],  # wording is not a contract
            "pipeline": {"name": "staff-detector", "version": "2026-07-22"},
        }
    ]


def test_versions_of_one_pipeline_are_listed(
    client: TestClient, registry: ProviderRegistry, alice: dict[str, str]
) -> None:
    registry.record(orchestrator_announcement(version="1.0.0"))
    registry.record(orchestrator_announcement(instance_id="orchestrator-2", version="2.0.0"))
    registry.record(worker_announcement())

    body = client.get("/pipelines/hello-world", headers=alice).json()

    assert [entry["version"] for entry in body["pipelines"]] == ["1.0.0", "2.0.0"]


def test_an_unknown_pipeline_name_is_a_404(
    client: TestClient, registry: ProviderRegistry, alice: dict[str, str]
) -> None:
    registry.record(orchestrator_announcement())

    assert client.get("/pipelines/nothing-like-this", headers=alice).status_code == 404
