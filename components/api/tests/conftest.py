from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from musibot.api.app import create_app
from musibot.api.config import ApiSettings
from tests.fakes import FakeStorage

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
def client(tokens_file: Path, storage: FakeStorage) -> TestClient:
    settings = ApiSettings.for_testing(api_tokens_file=tokens_file)
    return TestClient(create_app(settings, storage=storage))


@pytest.fixture
def alice() -> dict[str, str]:
    return {"Authorization": f"Bearer {ALICE_TOKEN}"}


@pytest.fixture
def bob() -> dict[str, str]:
    return {"Authorization": f"Bearer {BOB_TOKEN}"}
