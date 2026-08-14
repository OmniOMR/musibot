"""Running a *Pipeline* in a test, with no broker, no object storage and no
*Models*.

This is part of what the *Orchestrator Head* offers rather than a convenience
for its own test suite. A *Pipeline* is ordinary python that happens to be
plugged into a distributed system, and it should be testable the way ordinary
python is::

    def test_it_writes_a_layout() -> None:
        runner = PipelineRunner({"image.jpg": JPEG})
        runner.register_model(HELLO_MODEL, lambda call, files: files.update(
            {"transcription.musicxml": b"<score/>"}
        ))

        runner.run(HelloPipeline("hello-pipeline", "1.0.0", model=HELLO_MODEL),
                   input=["image.jpg"])

        assert "layout.json" in runner.files
        assert runner.model_calls[0].input == ["image.jpg"]

`run` is deliberately synchronous even though a *Pipeline* is a coroutine, so
that a *Pipeline* author needs no async test framework to write the test above.
Use `run_async` from a test that is already on an event loop.

A *Model* is whatever you say it is: the behaviour you register receives the
call and the page's *Files*, and may write into them exactly as a real *Model*
would. Raise from it to exercise the failure path.
"""

import asyncio
from collections.abc import Callable
from dataclasses import dataclass, field

from musibot.core.execution import NameAndVersion
from musibot.core.logs import LogLevel
from musibot.core.page import generate_page_id, validate_file_path

from musibot.orchestrator_head.pipeline import ModelExecutionFailed, Pipeline, PipelineContext
from musibot.orchestrator_head.storage import FileNotInPage


class UnexpectedModelExecution(Exception):
    """The *Pipeline* ran a *Model* the test did not register.

    A fault in the test rather than in the *Pipeline*, so it propagates out of
    `run` instead of becoming a `ModelExecutionFailed` the *Pipeline* might
    catch and paper over.
    """


@dataclass(frozen=True)
class ModelCall:
    """One `execute_model` a *Pipeline* made."""

    model: NameAndVersion
    input: list[str]
    parameters: dict[str, object]


@dataclass(frozen=True)
class LoggedLine:
    """One line a *Pipeline* said."""

    level: LogLevel
    message: str


ModelBehaviour = Callable[[ModelCall, dict[str, bytes]], None]
"""What a fake *Model* does: it is handed the call and the page's *Files*, and
may write into them. Raising fails the execution, message and all."""


def _writes_nothing(call: ModelCall, files: dict[str, bytes]) -> None:
    """The default behaviour: the *Model* succeeds and produces no *Files*."""


class _PageFiles:
    """A `PageStoragePort` over a dict, sharing it with the runner."""

    def __init__(self, files: dict[str, bytes]):
        self._files = files

    def read(self, page_id: str, file_path: str) -> bytes:
        try:
            return self._files[validate_file_path(file_path)]
        except KeyError:
            raise FileNotInPage(f"The file {file_path!r} is not in the page {page_id!r}")

    def write(self, page_id: str, file_path: str, data: bytes) -> None:
        self._files[validate_file_path(file_path)] = data

    def list_files(self, page_id: str) -> list[str]:
        # Sorted, because real storage answers in lexicographic key order and a
        # test that passes against a dict's insertion order would be a test that
        # passes for the wrong reason.
        return sorted(self._files)

    def exists(self, page_id: str, file_path: str) -> bool:
        return validate_file_path(file_path) in self._files


@dataclass
class PipelineRunner:
    """Runs one *Pipeline* against an in-memory *MusicorpusPage*.

    It stands in for the whole *Orchestrator Head*: it is the storage the
    *Pipeline* reads and writes, the log it talks to, and the *Models* it
    invokes. Afterwards the attributes below are what the *Pipeline* did.
    """

    files: dict[str, bytes] = field(default_factory=dict)
    """The page, before and after — seed it here and assert on it afterwards."""

    page_id: str = field(default_factory=generate_page_id)
    execution_id: int = 1

    logs: list[LoggedLine] = field(default_factory=list)
    """Every line the *Pipeline* logged, in order."""

    model_calls: list[ModelCall] = field(default_factory=list)
    """Every *Model* the *Pipeline* ran, in the order the calls were made."""

    written: list[str] = field(default_factory=list)
    """Every *File* path the *Pipeline* wrote, in order, including rewrites."""

    _models: dict[tuple[str, str], ModelBehaviour] = field(default_factory=dict)

    # --- setting the test up -------------------------------------------------

    def register_model(
        self, model: NameAndVersion, behaviour: ModelBehaviour = _writes_nothing
    ) -> None:
        """Say what one *Model* does when the *Pipeline* runs it.

        A *Pipeline* that runs a *Model* which was not registered raises
        `UnexpectedModelExecution` — a *Pipeline* silently invoking something
        the test did not think about should not look like a pass.
        """
        self._models[(model.name, model.version)] = behaviour

    # --- running it ----------------------------------------------------------

    def run(
        self,
        pipeline: Pipeline,
        *,
        input: list[str] | None = None,
        parameters: dict[str, object] | None = None,
    ) -> None:
        """Run the *Pipeline* to completion, synchronously.

        Whatever it raises comes out of here, which is how a test asserts on a
        failure. Call `run_async` instead from a test already on a loop.
        """
        asyncio.run(self.run_async(pipeline, input=input, parameters=parameters))

    async def run_async(
        self,
        pipeline: Pipeline,
        *,
        input: list[str] | None = None,
        parameters: dict[str, object] | None = None,
    ) -> None:
        """Run the *Pipeline* to completion on the current event loop."""
        file_paths = list(input or [])

        # The same check the `api` service makes before dispatching, so that a
        # test cannot hand a Pipeline an input list a User could never send —
        # and so that a malformed Signature is caught here rather than at
        # announcement time.
        pipeline.description().signature.check_input(file_paths)

        await pipeline.execute(
            PipelineContext(
                page_id=self.page_id,
                execution_id=self.execution_id,
                input=file_paths,
                parameters=dict(parameters or {}),
                storage=_PageFiles(self.files),
                runtime=self,
            )
        )

    # --- what the Pipeline sees of the head ----------------------------------

    def log(self, message: str, level: LogLevel) -> None:
        self.logs.append(LoggedLine(level=level, message=message))

    def files_written(self, file_paths: list[str]) -> None:
        self.written.extend(file_paths)

    async def execute_model(
        self, model: NameAndVersion, input: list[str], parameters: dict[str, object]
    ) -> None:
        call = ModelCall(model=model, input=input, parameters=parameters)
        self.model_calls.append(call)

        behaviour = self._models.get((model.name, model.version))
        if behaviour is None:
            raise UnexpectedModelExecution(
                f"The pipeline ran the model {model.name!r} version {model.version!r}, "
                f"which this test did not register"
            )

        try:
            behaviour(call, self.files)
        except Exception as failure:
            # Exactly what a Worker Head does with a Model that reports `failed`:
            # the reason becomes the message a Pipeline sees.
            raise ModelExecutionFailed(model, str(failure)) from failure

    # --- reading the result --------------------------------------------------

    def log_messages(self) -> list[str]:
        """Just the text of what was logged, which is usually what a test wants."""
        return [line.message for line in self.logs]
