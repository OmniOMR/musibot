"""Configuration of a *Worker Head*."""

from pathlib import Path
from typing import Any, Self

from musibot.core import LoggingSettings, RabbitSettings, S3Settings


class WorkerHeadSettings(RabbitSettings, S3Settings, LoggingSettings):
    """Everything a *Worker Head* is configured with.

    The shared connection blocks come from `core`; what is specific to a
    *Worker Head* is how to launch its one *Model* and where to stage the
    *Files* that model reads and writes.
    """

    # The command that launches the Model, split like a shell would split it.
    # Usually an absolute path into the model's own virtual environment, which
    # may be a different python from this process's — see docs/deployment.md.
    model_command: str

    # Where the local mirror of the Musicorpus pages lives, handed to the Model
    # as MUSIBOT_PAGES_DIR. A temporary directory is made when this is unset,
    # which is the normal case: the mirror is scratch space, not storage.
    pages_dir: Path | None = None

    # How long to wait for the Model to say `ready`. Generous, because this is
    # where a model loads its weights — a minute of silence at startup is
    # ordinary, and the Worker simply is not offered work during it.
    model_ready_timeout_seconds: float = 300.0

    @classmethod
    def for_testing(cls, **overrides: Any) -> Self:
        """Settings for a test, built without touching argv, env or any file."""
        return cls(_cli_parse_args=[], _env_file=None, **overrides)
