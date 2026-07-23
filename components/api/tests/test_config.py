from pathlib import Path

import pytest

from musibot.api.config import DEV_TOKEN, DEV_USER, ApiSettings


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
