from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from musibot.api.app import create_app
from musibot.api.config import ApiSettings
from musibot.api.discovery import ProviderRegistry
from musibot.api.domain import MusicorpusPageRepository
from tests.fakes import FakePublisher, FakeStorage

ALICE_TOKEN = "alice-token"
BOB_TOKEN = "bob-token"


@pytest.fixture
def tokens_file(tmp_path: Path) -> Path:
    path = tmp_path / "tokens.json"
    path.write_text(f'{{"{ALICE_TOKEN}": "alice", "{BOB_TOKEN}": "bob"}}')
    return path


@pytest.fixture
def storage() -> FakeStorage:
    return FakeStorage()


@pytest.fixture
def publisher() -> FakePublisher:
    return FakePublisher()


@pytest.fixture
def repository() -> MusicorpusPageRepository:
    return MusicorpusPageRepository()


@pytest.fixture
def registry() -> ProviderRegistry:
    """An empty registry the test fills by recording announcements itself,
    standing in for what would arrive over RabbitMQ."""
    return ProviderRegistry()


@pytest.fixture
def client(
    tokens_file: Path,
    storage: FakeStorage,
    publisher: FakePublisher,
    repository: MusicorpusPageRepository,
    registry: ProviderRegistry,
) -> Iterator[TestClient]:
    settings = ApiSettings.for_testing(api_tokens_file=tokens_file)
    app = create_app(
        settings,
        pages_repository=repository,
        registry=registry,
        storage=storage,
        publisher=publisher,
    )
    # The context manager runs the lifespan, so timeout timers are cancelled on
    # teardown; no real broker is attached, so nothing reaches for RabbitMQ.
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def alice() -> dict[str, str]:
    return {"Authorization": f"Bearer {ALICE_TOKEN}"}


@pytest.fixture
def bob() -> dict[str, str]:
    return {"Authorization": f"Bearer {BOB_TOKEN}"}
