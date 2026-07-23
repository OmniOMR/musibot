"""The configuration framework shared by all Musibot services.

Every Musibot service is configured from three sources, later ones winning:
the config file (a dotenv file), environment variables prefixed ``MUSIBOT_``,
and command line arguments. See ``docs/service-configuration.md``.

A service defines its settings by subclassing :class:`MusibotSettings`, mixing
in the shared connection blocks it needs, and calling
:meth:`MusibotSettings.load` once at startup::

    class WorkerHeadSettings(RabbitSettings, S3Settings, LoggingSettings):
        model_name: str
        model_command: str

    settings = WorkerHeadSettings.load()
"""

import argparse
import os
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Literal, Self

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ENV_PREFIX = "MUSIBOT_"

CONFIG_FILE_ENV_VAR = ENV_PREFIX + "CONFIG_FILE"


class MusibotSettings(BaseSettings):
    """Base class for the settings of any Musibot service."""

    model_config = SettingsConfigDict(
        env_prefix=ENV_PREFIX,
        cli_kebab_case=True,
        cli_avoid_json=True,
        extra="ignore",
        # Command line parsing is opt-in, performed by `load()` alone. Merely
        # constructing a settings object — in a test, or programmatically —
        # must never reach for the surrounding process's argv.
        cli_parse_args=False,
    )

    config_file: Path | None = Field(
        default=None,
        description="Path to a dotenv file holding configuration.",
    )

    @classmethod
    def load(cls, argv: Sequence[str] | None = None, env: Mapping[str, str] | None = None) -> Self:
        """Load the settings from the command line, the environment and the config file.

        Pass `argv` and `env` explicitly in tests; in a service, leave them out
        and the process's own command line and environment are used.
        """
        arguments = list(argv) if argv is not None else None
        environment: Mapping[str, str] = env if env is not None else os.environ

        config_file = _resolve_config_file(arguments, environment)

        return cls(
            _cli_parse_args=arguments if arguments is not None else True,
            _env_file=config_file,
        )

    def describe(self) -> str:
        """Render the effective configuration, with secrets masked.

        Logged by every service at startup — the single most useful line in the
        log when a service turns out to be talking to the wrong host.
        """
        lines = []
        for name in type(self).model_fields:
            value = getattr(self, name)
            if isinstance(value, SecretStr):
                rendered = "***" if value.get_secret_value() else "(empty)"
            else:
                rendered = str(value)
            lines.append(f"  {name} = {rendered}")
        return "\n".join(lines)


def _resolve_config_file(argv: Sequence[str] | None, env: Mapping[str, str]) -> Path | None:
    """Find the config file before the settings themselves can be loaded.

    The config file is one of the settings, yet it has to be known before the
    others can be read out of it — so it is resolved up front, from the command
    line and the environment only.
    """
    path: str | None = None

    if argv is not None:
        parser = argparse.ArgumentParser(add_help=False)
        parser.add_argument("--config-file")
        known, _ = parser.parse_known_args(list(argv))
        path = known.config_file

    if path is None:
        path = env.get(CONFIG_FILE_ENV_VAR)

    if path is None:
        return None

    resolved = Path(path)
    if not resolved.is_file():
        # A missing dotenv file is silently ignored by the settings machinery,
        # which would leave a service running on defaults while its operator
        # believes it is configured. Refuse instead.
        raise FileNotFoundError(f"Config file does not exist: {resolved}")

    return resolved


class RabbitSettings(MusibotSettings):
    """Connection to RabbitMQ. Needed by every service."""

    rabbit_host: str = "localhost"
    rabbit_port: int = 5672
    rabbit_user: str = "root"
    rabbit_password: SecretStr = SecretStr("password")
    rabbit_vhost: str = "/"


class S3Settings(MusibotSettings):
    """Connection to MinIO. Needed by every service that touches Files."""

    s3_endpoint_url: str = "http://localhost:9000"
    s3_access_key: str = "root"
    s3_secret_key: SecretStr = SecretStr("password")
    s3_bucket: str = "musibot-pages"

    s3_public_url: str | None = Field(
        default=None,
        description=(
            "The address presigned URLs are issued against, when it differs "
            "from the endpoint this service itself uses. Defaults to that endpoint."
        ),
    )

    @model_validator(mode="after")
    def _default_public_url_to_endpoint(self) -> Self:
        # In production the two differ: MinIO is reached internally by the
        # service and publicly by the User redeeming a presigned URL. In
        # development they are the same address.
        if self.s3_public_url is None:
            self.s3_public_url = self.s3_endpoint_url
        return self


class LoggingSettings(MusibotSettings):
    """Logging. Needed by every service."""

    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    log_format: Literal["text", "json"] = "text"
