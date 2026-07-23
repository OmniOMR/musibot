"""The pipeline-execution HTTP endpoints, over the TestClient with a fake broker."""

from pathlib import Path

from fastapi.testclient import TestClient
from musibot.core.execution import (
    PIPELINE_EXECUTIONS_EXCHANGE,
    PipelineExecutionStart,
    parse_pipeline_execution_message,
    routing_key,
)

from musibot.api.domain import MusicorpusPageRepository
from tests.fakes import FakePublisher


def make_page(client: TestClient, headers: dict[str, str]) -> str:
    return str(client.post("/musicorpus-pages", headers=headers).json()["page_id"])


def start_body() -> dict[str, object]:
    return {"pipeline_name": "hello-world", "pipeline_version": "1.0.0", "parameters": {}}


def test_start_a_pipeline_execution(
    client: TestClient, alice: dict[str, str], publisher: FakePublisher
) -> None:
    page_id = make_page(client, alice)

    response = client.post(
        f"/musicorpus-pages/{page_id}/pipeline-executions", headers=alice, json=start_body()
    )

    assert response.status_code == 201
    body = response.json()
    assert body["execution_id"] == 1
    assert body["state"] == "running"
    assert body["pipeline_name"] == "hello-world"

    # It was dispatched to orchestrators on the right exchange and routing key.
    [message] = publisher.published
    assert message.exchange == PIPELINE_EXECUTIONS_EXCHANGE
    assert message.routing_key == routing_key("hello-world", "1.0.0")
    start = parse_pipeline_execution_message(message.body)
    assert isinstance(start, PipelineExecutionStart)
    assert start.page_id == page_id


def test_execution_ids_increment_per_page(client: TestClient, alice: dict[str, str]) -> None:
    page_id = make_page(client, alice)

    first = client.post(
        f"/musicorpus-pages/{page_id}/pipeline-executions", headers=alice, json=start_body()
    ).json()
    second = client.post(
        f"/musicorpus-pages/{page_id}/pipeline-executions", headers=alice, json=start_body()
    ).json()

    assert (first["execution_id"], second["execution_id"]) == (1, 2)


def test_list_pipeline_executions(client: TestClient, alice: dict[str, str]) -> None:
    page_id = make_page(client, alice)
    client.post(
        f"/musicorpus-pages/{page_id}/pipeline-executions", headers=alice, json=start_body()
    )

    response = client.get(f"/musicorpus-pages/{page_id}/pipeline-executions", headers=alice)

    assert response.status_code == 200
    assert [e["execution_id"] for e in response.json()] == [1]


def test_fetch_one_pipeline_execution(client: TestClient, alice: dict[str, str]) -> None:
    page_id = make_page(client, alice)
    client.post(
        f"/musicorpus-pages/{page_id}/pipeline-executions", headers=alice, json=start_body()
    )

    response = client.get(f"/musicorpus-pages/{page_id}/pipeline-executions/1", headers=alice)

    assert response.status_code == 200
    assert response.json()["execution_id"] == 1


def test_polling_reflects_a_settled_execution(
    client: TestClient, alice: dict[str, str], repository: MusicorpusPageRepository
) -> None:
    page_id = make_page(client, alice)
    client.post(
        f"/musicorpus-pages/{page_id}/pipeline-executions", headers=alice, json=start_body()
    )

    # Simulate the result consumer having settled the execution.
    repository.get(page_id).executions[1].state = "completed"

    response = client.get(f"/musicorpus-pages/{page_id}/pipeline-executions/1", headers=alice)
    assert response.json()["state"] == "completed"


def test_fetching_a_missing_execution_is_404(client: TestClient, alice: dict[str, str]) -> None:
    page_id = make_page(client, alice)

    assert (
        client.get(f"/musicorpus-pages/{page_id}/pipeline-executions/99", headers=alice).status_code
        == 404
    )


def test_deleting_a_page_terminates_its_running_execution(
    client: TestClient, alice: dict[str, str], publisher: FakePublisher
) -> None:
    from musibot.core.execution import PIPELINE_EXECUTION_CONTROL_EXCHANGE

    page_id = make_page(client, alice)
    client.post(
        f"/musicorpus-pages/{page_id}/pipeline-executions", headers=alice, json=start_body()
    )

    client.delete(f"/musicorpus-pages/{page_id}", headers=alice)

    assert any(m.exchange == PIPELINE_EXECUTION_CONTROL_EXCHANGE for m in publisher.published)


# --- Auth and ownership ------------------------------------------------------


def test_starting_needs_ownership(
    client: TestClient, alice: dict[str, str], bob: dict[str, str]
) -> None:
    page_id = make_page(client, alice)

    response = client.post(
        f"/musicorpus-pages/{page_id}/pipeline-executions", headers=bob, json=start_body()
    )

    assert response.status_code == 404


def test_starting_needs_auth(client: TestClient, alice: dict[str, str]) -> None:
    page_id = make_page(client, alice)

    response = client.post(f"/musicorpus-pages/{page_id}/pipeline-executions", json=start_body())

    assert response.status_code == 401


def test_executions_unavailable_without_a_broker(tokens_file: Path, alice: dict[str, str]) -> None:
    from musibot.api.app import create_app
    from musibot.api.config import ApiSettings

    # A service running without a broker: pages work, execution reports 503.
    with TestClient(create_app(ApiSettings.for_testing(api_tokens_file=tokens_file))) as client:
        page_id = make_page(client, alice)
        response = client.post(
            f"/musicorpus-pages/{page_id}/pipeline-executions", headers=alice, json=start_body()
        )

    assert response.status_code == 503
