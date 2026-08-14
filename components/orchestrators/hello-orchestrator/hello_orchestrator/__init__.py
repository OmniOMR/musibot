"""An *Orchestrator* that provides one *Pipeline* and proves the plumbing works.

It exists so that the *Orchestrator* half of Musibot can be exercised end to end
without any real recognition in the way — and so that there is one worked
example of the [Orchestrator Head API](../../orchestrator-head/README.md) to
read. It is the counterpart of `hello-model` on the other side of the system.

The startup script below is the whole of what an *Orchestrator* is: load the
settings, build the *Pipelines* from them, register them, run.
"""

from musibot.orchestrator_head import NameAndVersion, Orchestrator, OrchestratorHeadSettings

from hello_orchestrator.pipeline import HelloPipeline

__all__ = ["HelloOrchestratorSettings", "HelloPipeline", "main"]

ORCHESTRATOR_NAME = "hello-orchestrator"

PIPELINE_NAME = "hello-pipeline"
PIPELINE_VERSION = "1.0.0"

MODEL_NAME = "hello-model"


class HelloOrchestratorSettings(OrchestratorHeadSettings):
    """What this *Orchestrator* is configured with, beyond the shared blocks.

    Both of these become registration parameters of the one *Pipeline*, which is
    what they are here to demonstrate: a *Pipeline* is parametrized by its
    *Orchestrator*, and an *Orchestrator* is parametrized by its command line,
    its environment and its config file (see
    `docs/service-configuration.md`).
    """

    hello_model_version: str = "1.0.0"
    """Which snapshot of `hello-model` the *Pipeline* pins. A real *Pipeline*
    pins a *Model* the same way, and this is how the same implementation is
    registered twice — once against the stable snapshot and once against the
    one being developed."""

    staff_margin: int = 20
    """How far the made-up staff sits from each edge of the image, in pixels."""


def main() -> None:
    """Run the hello orchestrator until it is stopped."""
    settings = HelloOrchestratorSettings.load()

    orchestrator = Orchestrator(ORCHESTRATOR_NAME, settings)
    orchestrator.register_pipeline(
        HelloPipeline(
            PIPELINE_NAME,
            PIPELINE_VERSION,
            model=NameAndVersion(name=MODEL_NAME, version=settings.hello_model_version),
            margin=settings.staff_margin,
        )
    )
    orchestrator.run()
