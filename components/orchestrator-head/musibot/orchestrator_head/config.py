"""Configuration of an *Orchestrator Head*.

An *Orchestrator* extends this with its own settings — which *Model* version a
*Pipeline* pins, where some resource lives — and gets the command line
arguments, environment variables and config-file keys for them for free::

    class OmniOmrSettings(OrchestratorHeadSettings):
        zeus_version: str = "2026-07-22"

    settings = OmniOmrSettings.load()

That is where a *Pipeline's* registration parameters come from, and the reason
settings are loaded before the *Pipelines* are constructed rather than inside
`Orchestrator.run()`. See `docs/writing-pipelines.md`.
"""

from typing import Any, Self

from musibot.core import LoggingSettings, RabbitSettings, S3Settings


class OrchestratorHeadSettings(RabbitSettings, S3Settings, LoggingSettings):
    """Everything an *Orchestrator Head* is configured with.

    Nothing here is required: the shared connection blocks come from `core` and
    default to the local development stack, so an *Orchestrator* started against
    it takes no arguments at all.

    Which *Pipelines* it provides is deliberately not configuration — they are
    registered in code, because a *Pipeline* is code.
    """

    # How many Pipeline Executions this process runs at once, as the broker's
    # prefetch. Higher than a Worker Head's 1 because a Pipeline spends most of
    # its life awaiting Models rather than computing, so one process can carry
    # several — and lower than it might be because the ones that do compute
    # (OpenCV, image slicing) hold the event loop's threadpool while they do.
    # More than this and the excess stays in the shared queue, where another
    # instance of the same Orchestrator is free to take it.
    max_concurrent_executions: int = 4

    @classmethod
    def for_testing(cls, **overrides: Any) -> Self:
        """Settings for a test, built without touching argv, env or any file."""
        return cls(_cli_parse_args=[], _env_file=None, **overrides)
