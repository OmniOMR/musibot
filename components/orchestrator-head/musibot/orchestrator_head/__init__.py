"""The Musibot interface layer that one *Orchestrator* runs inside.

Everything a *Pipeline* author needs is re-exported here, `core`'s `Signature`
and `NameAndVersion` included, so that writing an *Orchestrator* is one import::

    from musibot.orchestrator_head import NameAndVersion, Pipeline, PipelineContext, Signature

See `docs/writing-pipelines.md`.
"""

from musibot.core.discovery import Signature
from musibot.core.execution import NameAndVersion

from musibot.orchestrator_head.config import OrchestratorHeadSettings
from musibot.orchestrator_head.pipeline import (
    ExecutionLog,
    ExecutionRuntime,
    InvalidPipeline,
    ModelExecutionFailed,
    Pipeline,
    PipelineContext,
)
from musibot.orchestrator_head.storage import FileNotInPage, PageStorage, PageStoragePort

__all__ = [
    "ExecutionLog",
    "ExecutionRuntime",
    "FileNotInPage",
    "InvalidPipeline",
    "ModelExecutionFailed",
    "NameAndVersion",
    "OrchestratorHeadSettings",
    "PageStorage",
    "PageStoragePort",
    "Pipeline",
    "PipelineContext",
    "Signature",
]
