from pathlib import Path

import pytest

from musibot.api.config import DEV_TOKEN, DEV_USER, ApiSettings
from tests.conftest import ClientBuilder


def test_dev_token_is_used_when_no_file_is_configured() -> None:
    settings = ApiSettings.for_testing()

    assert settings.load_api_tokens() == {DEV_TOKEN: DEV_USER}


def test_tokens_are_loaded_from_the_configured_file(tmp_path: Path) -> None:
    path = tmp_path / "tokens.json"
    path.write_text('{"tok-a": "alice", "tok-b": "bob"}')

    settings = ApiSettings.for_testing(api_tokens_file=path)

    assert settings.load_api_tokens() == {"tok-a": "alice", "tok-b": "bob"}


def test_a_missing_tokens_file_is_an_error(tmp_path: Path) -> None:
    settings = ApiSettings.for_testing(api_tokens_file=tmp_path / "absent.json")

    with pytest.raises(RuntimeError):
        settings.load_api_tokens()


def test_a_malformed_tokens_file_is_an_error(tmp_path: Path) -> None:
    path = tmp_path / "tokens.json"
    path.write_text("not json at all")

    settings = ApiSettings.for_testing(api_tokens_file=path)

    with pytest.raises(RuntimeError):
        settings.load_api_tokens()


def test_a_tokens_file_of_the_wrong_shape_is_an_error(tmp_path: Path) -> None:
    path = tmp_path / "tokens.json"
    path.write_text('["not", "a", "map"]')

    settings = ApiSettings.for_testing(api_tokens_file=path)

    with pytest.raises(RuntimeError):
        settings.load_api_tokens()


def test_an_empty_tokens_file_is_an_error(tmp_path: Path) -> None:
    path = tmp_path / "tokens.json"
    path.write_text("{}")

    settings = ApiSettings.for_testing(api_tokens_file=path)

    with pytest.raises(RuntimeError):
        settings.load_api_tokens()


def test_settings_default_to_the_documented_port() -> None:
    assert ApiSettings.for_testing().port == 8080


def test_no_root_path_by_default(build_client: ClientBuilder) -> None:
    with build_client() as client:
        assert "servers" not in client.get("/openapi.json").json()


def test_a_root_path_is_announced_in_the_openapi_document(build_client: ClientBuilder) -> None:
    """What makes the interactive docs work behind a path prefix.

    nginx strips the prefix before the request arrives, so routing is
    unaffected either way and no ordinary request would notice this being
    wrong. `/docs` would: it is a page that fetches its own schema, and
    without this it asks the origin root for it and renders empty.
    """
    with build_client(root_path="/musibot/api") as client:
        spec = client.get("/openapi.json").json()

        assert spec["servers"] == [{"url": "/musibot/api"}]

    # Routes are still declared and served at the root — the prefix describes
    # where the world reaches the service, not where it listens.
    with build_client(root_path="/musibot/api") as client:
        assert client.get("/health").json() == {"status": "ok"}
