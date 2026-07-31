"""Configuration of the `api` service."""

import json
import logging
from pathlib import Path
from typing import Any, Self

from musibot.core import LoggingSettings, RabbitSettings, S3Settings

from musibot.api.domain import PUBLIC_IDENTITY_PREFIX, is_public_identity

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

    # --- the General public tier ------------------------------------------
    # See docs/public-access.md. The defence is the global pair below: they
    # cap the public as one pool, which is what keeps a Library's batch run
    # from being starved. The per-session pair guards against carelessness
    # rather than malice — minting a session is free, so anyone can have
    # another one.

    # Whether POST /public-sessions mints anything at all. Off by default, so
    # a Libraries-only deployment does not acquire a public demo by accident.
    public_access_enabled: bool = False

    # Global: how many Pipeline Executions all public sessions together may
    # have running. Size it against the Worker fleet — the public can occupy
    # this many Workers, so a Library run proceeds at (N-K)/N of full speed.
    # Keep it above 1, or one public user holds the whole public tier.
    public_max_concurrent_executions: int = 2

    # Global: how much of MinIO public pages may hold between them. Measured
    # after the fact by the sweep (this service never sees File bytes), so it
    # can be overshot by a sweep interval's worth of uploads — set it well
    # under what the disk actually has.
    public_storage_quota_bytes: int = 5 * 1024**3

    # How long a Public Session and its pages live, from the moment it is
    # minted. Deliberately not extended by use: an expired session is a
    # reload, and a sliding one that the Web UI's polling kept refreshing
    # would never expire at all.
    public_session_ttl_seconds: float = 3600.0

    # How often expired sessions are swept and public storage re-measured.
    public_sweep_interval_seconds: float = 60.0

    # The ceiling on a public Pipeline Execution, applied on top of
    # pipeline_execution_timeout_seconds rather than instead of it: together
    # with the global cap it bounds public occupancy of the Worker fleet.
    public_execution_timeout_seconds: float = 60.0

    # Per session, both of them courtesy caps.
    public_max_pages_per_session: int = 5
    public_max_concurrent_executions_per_session: int = 1

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

        # Public sessions live in the same identity space as these users, under
        # a reserved prefix. A configured user wearing that prefix would be
        # taken for a public one — losing their exemption from the public caps,
        # and worse, letting them see pages a public session created.
        reserved = sorted(user for user in tokens.values() if is_public_identity(user))
        if reserved:
            raise RuntimeError(
                f"api_tokens_file {self.api_tokens_file} names users starting with "
                f"{PUBLIC_IDENTITY_PREFIX!r}, which is reserved for public sessions: "
                f"{', '.join(repr(user) for user in reserved)}"
            )

        return tokens

    @classmethod
    def for_testing(cls, **overrides: Any) -> Self:
        """Settings for a test, built without touching argv, env or any file."""
        return cls(_cli_parse_args=[], _env_file=None, **overrides)
