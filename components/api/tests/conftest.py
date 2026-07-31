from collections.abc import Iterator
from contextlib import AbstractContextManager, contextmanager
from pathlib import Path
from typing import Any, Protocol, cast

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from musibot.api.app import create_app
from musibot.api.config import ApiSettings
from musibot.api.discovery import ProviderRegistry
from musibot.api.domain import MusicorpusPageRepository
from musibot.api.public import PublicAccess
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


class ClientBuilder(Protocol):
    """Builds a client against settings a test chooses. See `build_client`."""

    def __call__(self, **overrides: Any) -> "AbstractContextManager[TestClient]": ...


@pytest.fixture
def build_client(
    tokens_file: Path,
    storage: FakeStorage,
    publisher: FakePublisher,
    repository: MusicorpusPageRepository,
    registry: ProviderRegistry,
) -> ClientBuilder:
    """A client whose settings the test picks — for the ones about a setting.

    The collaborators are the same fixtures the plain `client` uses, so a test
    can inspect the storage or the repository it handed over.
    """

    @contextmanager
    def build(**overrides: Any) -> Iterator[TestClient]:
        settings = ApiSettings.for_testing(api_tokens_file=tokens_file, **overrides)
        app = create_app(
            settings,
            pages_repository=repository,
            registry=registry,
            storage=storage,
            publisher=publisher,
        )
        # The context manager runs the lifespan, so timeout timers and the
        # public sweep are cancelled on teardown; no real broker is attached, so
        # nothing reaches for RabbitMQ.
        with TestClient(app) as test_client:
            yield test_client

    return build


@pytest.fixture
def client(build_client: ClientBuilder) -> Iterator[TestClient]:
    with build_client() as test_client:
        yield test_client


def public_access_of(client: TestClient) -> PublicAccess:
    """The public tier the app was built with, for a test to sweep by hand."""
    return cast(PublicAccess, cast(FastAPI, client.app).state.public_access)


@pytest.fixture
def alice() -> dict[str, str]:
    return {"Authorization": f"Bearer {ALICE_TOKEN}"}


@pytest.fixture
def bob() -> dict[str, str]:
    return {"Authorization": f"Bearer {BOB_TOKEN}"}
