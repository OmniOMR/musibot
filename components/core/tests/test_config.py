from pathlib import Path

import pytest
from pydantic import SecretStr

from musibot.core.config import LoggingSettings, MusibotSettings, RabbitSettings, S3Settings


class ExampleSettings(RabbitSettings, S3Settings, LoggingSettings):
    """A service's settings look like this: shared blocks plus its own fields."""

    model_name: str = "unnamed-model"


def config_file(tmp_path: Path, contents: str) -> Path:
    path = tmp_path / "musibot.env"
    path.write_text(contents)
    return path


def test_defaults_match_the_development_stack() -> None:
    settings = ExampleSettings.load(argv=[], env={})

    assert settings.rabbit_host == "localhost"
    assert settings.rabbit_port == 5672
    assert settings.s3_endpoint_url == "http://localhost:9000"
    assert settings.s3_bucket == "musibot-pages"
    assert settings.log_level == "INFO"


def test_settings_come_from_the_command_line() -> None:
    settings = ExampleSettings.load(
        argv=["--rabbit-host", "cli-host", "--rabbit-port", "1111"],
        env={},
    )

    assert settings.rabbit_host == "cli-host"
    assert settings.rabbit_port == 1111


def test_settings_come_from_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MUSIBOT_RABBIT_HOST", "env-host")

    settings = ExampleSettings.load(argv=[])

    assert settings.rabbit_host == "env-host"


def test_settings_come_from_the_config_file(tmp_path: Path) -> None:
    path = config_file(tmp_path, "MUSIBOT_RABBIT_HOST=file-host\nMUSIBOT_RABBIT_PORT=2222\n")

    settings = ExampleSettings.load(argv=["--config-file", str(path)], env={})

    assert settings.rabbit_host == "file-host"
    assert settings.rabbit_port == 2222


def test_the_config_file_may_be_named_by_the_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = config_file(tmp_path, "MUSIBOT_RABBIT_HOST=file-host\n")
    monkeypatch.setenv("MUSIBOT_CONFIG_FILE", str(path))

    settings = ExampleSettings.load(argv=[])

    assert settings.rabbit_host == "file-host"


def test_the_environment_beats_the_config_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = config_file(tmp_path, "MUSIBOT_RABBIT_HOST=file-host\nMUSIBOT_RABBIT_PORT=2222\n")
    monkeypatch.setenv("MUSIBOT_RABBIT_HOST", "env-host")

    settings = ExampleSettings.load(argv=["--config-file", str(path)])

    assert settings.rabbit_host == "env-host"
    assert settings.rabbit_port == 2222  # untouched by the environment


def test_the_command_line_beats_everything(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = config_file(tmp_path, "MUSIBOT_RABBIT_HOST=file-host\n")
    monkeypatch.setenv("MUSIBOT_RABBIT_HOST", "env-host")

    settings = ExampleSettings.load(argv=["--config-file", str(path), "--rabbit-host", "cli-host"])

    assert settings.rabbit_host == "cli-host"


def test_a_missing_config_file_is_refused(tmp_path: Path) -> None:
    missing = tmp_path / "nope.env"

    # Silently ignoring it would leave the service on defaults while its
    # operator believes it is configured.
    with pytest.raises(FileNotFoundError):
        ExampleSettings.load(argv=["--config-file", str(missing)], env={})


def test_no_config_file_is_searched_for_implicitly(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / ".env").write_text("MUSIBOT_RABBIT_HOST=stray-host\n")
    monkeypatch.chdir(tmp_path)

    settings = ExampleSettings.load(argv=[], env={})

    assert settings.rabbit_host == "localhost"


def test_a_malformed_value_fails_at_startup() -> None:
    with pytest.raises(ValueError):
        ExampleSettings.load(argv=["--rabbit-port", "not-a-port"], env={})


def test_an_unknown_command_line_argument_is_refused() -> None:
    with pytest.raises(SystemExit):
        ExampleSettings.load(argv=["--rabbit-hostt", "typo"], env={})


def test_service_specific_fields_sit_beside_the_shared_blocks() -> None:
    settings = ExampleSettings.load(argv=["--model-name", "staff-detector"], env={})

    assert settings.model_name == "staff-detector"
    assert settings.rabbit_host == "localhost"


def test_the_public_s3_url_defaults_to_the_endpoint() -> None:
    settings = ExampleSettings.load(argv=["--s3-endpoint-url=http://minio.internal:9000"], env={})

    assert settings.s3_public_url == "http://minio.internal:9000"


def test_the_public_s3_url_may_differ_from_the_endpoint() -> None:
    settings = ExampleSettings.load(
        argv=[
            "--s3-endpoint-url=http://minio.internal:9000",
            "--s3-public-url=https://musibot.example.org/s3",
        ],
        env={},
    )

    assert settings.s3_endpoint_url == "http://minio.internal:9000"
    assert settings.s3_public_url == "https://musibot.example.org/s3"


def test_secrets_are_held_as_secrets() -> None:
    settings = ExampleSettings.load(argv=["--rabbit-password", "hunter2"], env={})

    assert isinstance(settings.rabbit_password, SecretStr)
    assert settings.rabbit_password.get_secret_value() == "hunter2"
    assert "hunter2" not in repr(settings)


def test_the_effective_configuration_is_described_with_secrets_masked() -> None:
    settings = ExampleSettings.load(
        argv=["--rabbit-host", "rabbit.internal", "--rabbit-password", "hunter2"],
        env={},
    )

    description = settings.describe()

    assert "rabbit_host = rabbit.internal" in description
    assert "rabbit_password = ***" in description
    assert "hunter2" not in description


def test_constructing_settings_does_not_read_the_command_line(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # A settings object built directly — in a test, or programmatically — must
    # not reach for the surrounding process's argv, which belongs to whatever
    # is running (pytest, for one).
    monkeypatch.setattr("sys.argv", ["pytest", "--rabbit-host", "argv-host"])

    settings = ExampleSettings()

    assert settings.rabbit_host == "localhost"


def test_the_base_class_carries_only_the_config_file_field() -> None:
    assert set(MusibotSettings.model_fields) == {"config_file"}
