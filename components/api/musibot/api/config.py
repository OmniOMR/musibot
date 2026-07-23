"""Configuration of the `api` service."""

import json
import logging
from pathlib import Path
from typing import Any, Self

from musibot.core import LoggingSettings, RabbitSettings, S3Settings

logger = logging.getLogger(__name__)

# The single token that works when none are configured. It matches the token
# used throughout the documentation and the local development stack, so a
# freshly started service is immediately usable — at the cost of being public
# knowledge, which is why using it is loudly warned about at startup.
DEV_TOKEN = "secret"
DEV_USER = "developer"


class ApiSettings(RabbitSettings, S3Settings, LoggingSettings):
    """Everything the `api` service is configured with.

    The shared connection blocks come from `core`; the fields here are the
    service's own.
    """

    host: str = "127.0.0.1"
    port: int = 8080

    # A JSON file mapping API token to the user it identifies:
    #   { "s3cr3t-token": "alice", "other-token": "bob" }
    # Kept out of the main config so the tokens are not mixed in with ordinary
    # settings, and so they can have their own file permissions. When unset, the
    # single development token is used (see above).
    api_tokens_file: Path | None = None

    # How long a Pipeline Execution may run before the service declares it timed
    # out. A ceiling over whatever a pipeline start requests.
    pipeline_execution_timeout_seconds: float = 300.0

    # How long a presigned upload/download URL stays valid. Long enough to
    # transfer a page scan on a slow link, short enough to limit a leaked URL.
    file_url_ttl_seconds: float = 900.0

    def load_api_tokens(self) -> dict[str, str]:
        """Read the configured token→user map, or fall back to the dev token.

        Called once at startup. Raises if the file is set but unreadable or
        malformed — a service that cannot load its tokens must not come up
        silently accepting none.
        """
        if self.api_tokens_file is None:
            logger.warning(
                "No api_tokens_file configured; accepting the built-in development "
                "token %r for user %r. Do not do this in production.",
                DEV_TOKEN,
                DEV_USER,
            )
            return {DEV_TOKEN: DEV_USER}

        try:
            raw = self.api_tokens_file.read_text()
        except OSError as error:
            raise RuntimeError(f"Cannot read api_tokens_file {self.api_tokens_file}: {error}")

        try:
            tokens = json.loads(raw)
        except json.JSONDecodeError as error:
            raise RuntimeError(f"api_tokens_file {self.api_tokens_file} is not valid JSON: {error}")

        if not isinstance(tokens, dict) or not all(
            isinstance(token, str) and isinstance(user, str) for token, user in tokens.items()
        ):
            raise RuntimeError(
                f"api_tokens_file {self.api_tokens_file} must be a JSON object of "
                "token strings to user strings"
            )

        if not tokens:
            raise RuntimeError(f"api_tokens_file {self.api_tokens_file} lists no tokens")

        return tokens

    @classmethod
    def for_testing(cls, **overrides: Any) -> Self:
        """Settings for a test, built without touching argv, env or any file."""
        return cls(_cli_parse_args=[], _env_file=None, **overrides)
