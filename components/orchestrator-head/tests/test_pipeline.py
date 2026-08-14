"""The API a *Pipeline* is written against, exercised the way one is.

Everything here goes through `PipelineRunner`, which is the same thing a
*Pipeline* author uses — so these tests are also the worked examples of it.
"""

import asyncio
from typing import Any

import pytest
from musibot.core.patterns import SignatureMismatch

from musibot.orchestrator_head import (
    InvalidPipeline,
    ModelExecutionFailed,
    NameAndVersion,
    Pipeline,
    PipelineContext,
    Signature,
)
from musibot.orchestrator_head.storage import FileNotInPage
from musibot.orchestrator_head.testing import (
    ModelCall,
    PipelineRunner,
    UnexpectedModelExecution,
)

HELLO_MODEL = NameAndVersion(name="hello-model", version="1.0.0")
OTHER_MODEL = NameAndVersion(name="hello-model", version="2.0.0")


class Doubling(Pipeline):
    """Reads `image.jpg`, writes it back doubled. The smallest useful pipeline."""

    name = "doubling"
    version = "1.0.0"
    signature = Signature(input=["image.jpg"], output=["doubled.bin"])

    async def execute(self, ctx: PipelineContext) -> None:
        data = await ctx.read_bytes("image.jpg")
        ctx.logger.info("read %d bytes", len(data))
        await ctx.write_bytes("doubled.bin", data * 2)


class RunsAModel(Pipeline):
    """A pipeline whose *Model* is a registration parameter.

    This is the shape the whole class-based API exists for: one implementation,
    registered twice under different names with different *Model* pins.
    """

    signature = Signature(input=["image.jpg"], output=["transcription.musicxml"])

    def __init__(self, name: str, version: str, *, model: NameAndVersion):
        self.name = name
        self.version = version
        self._model = model

    async def execute(self, ctx: PipelineContext) -> None:
        await ctx.execute_model(self._model, input=["image.jpg"])
        transcription = await ctx.read_text("transcription.musicxml")
        ctx.logger.info("the model wrote %d characters", len(transcription))


def transcribes(text: str) -> Any:
    """A fake *Model* that writes a transcription, as a real one would."""

    def behaviour(call: ModelCall, files: dict[str, bytes]) -> None:
        files["transcription.musicxml"] = text.encode("utf-8")

    return behaviour


# --- files -------------------------------------------------------------------


def test_a_pipeline_reads_and_writes_the_page() -> None:
    runner = PipelineRunner({"image.jpg": b"abc"})

    runner.run(Doubling(), input=["image.jpg"])

    assert runner.files["doubled.bin"] == b"abcabc"


def test_writing_announces_the_file_it_wrote() -> None:
    # What `musibot.file-changes` carries, so a User sees a File as it appears.
    runner = PipelineRunner({"image.jpg": b"abc"})

    runner.run(Doubling(), input=["image.jpg"])

    assert runner.written == ["doubled.bin"]


def test_reading_a_file_the_page_does_not_have_says_so() -> None:
    runner = PipelineRunner()

    with pytest.raises(FileNotInPage):
        runner.run(Doubling(), input=["image.jpg"])


def test_text_round_trips_through_the_page() -> None:
    class WritesText(Pipeline):
        name, version = "writes-text", "1.0.0"
        signature = Signature(output=["note.txt"])

        async def execute(self, ctx: PipelineContext) -> None:
            await ctx.write_text("note.txt", "hlásky — ěščř")
            assert await ctx.read_text("note.txt") == "hlásky — ěščř"

    runner = PipelineRunner()
    runner.run(WritesText())

    assert runner.files["note.txt"].decode("utf-8") == "hlásky — ěščř"


def test_a_pipeline_can_ask_what_the_page_holds() -> None:
    """How a *Pipeline* learns what a *Model* produced when it named the files.

    A splitter declaring `Staves/{*}/image.jpg` decides how many staves there
    are, so listing is the only way to find out.
    """
    seen: list[list[str]] = []

    class Lists(Pipeline):
        name, version = "lists", "1.0.0"
        signature = Signature(input=["image.jpg"])

        async def execute(self, ctx: PipelineContext) -> None:
            seen.append(await ctx.list_files())
            seen.append([path for path in await ctx.list_files() if await ctx.exists(path)])

    runner = PipelineRunner({"image.jpg": b"a", "Staves/2/image.jpg": b"b"})
    runner.run(Lists(), input=["image.jpg"])

    # Lexicographic, as a real listing answers — not the dict's insertion order.
    assert seen[0] == ["Staves/2/image.jpg", "image.jpg"]
    assert seen[1] == seen[0]


def test_a_file_the_page_does_not_hold_does_not_exist() -> None:
    class Checks(Pipeline):
        name, version = "checks", "1.0.0"
        signature = Signature()
        found: bool | None = None

        async def execute(self, ctx: PipelineContext) -> None:
            self.found = await ctx.exists("layout.json")

    pipeline = Checks()
    PipelineRunner().run(pipeline)

    assert pipeline.found is False


# --- logging -----------------------------------------------------------------


def test_the_log_takes_percent_arguments_like_logging_does() -> None:
    runner = PipelineRunner({"image.jpg": b"abc"})

    runner.run(Doubling(), input=["image.jpg"])

    assert runner.log_messages() == ["read 3 bytes"]


def test_every_level_reaches_the_log() -> None:
    class Chatters(Pipeline):
        name, version = "chatters", "1.0.0"
        signature = Signature()

        async def execute(self, ctx: PipelineContext) -> None:
            ctx.logger.debug("d")
            ctx.logger.info("i")
            ctx.logger.warning("w")
            ctx.logger.error("e")

    runner = PipelineRunner()
    runner.run(Chatters())

    assert [(line.level, line.message) for line in runner.logs] == [
        ("debug", "d"),
        ("info", "i"),
        ("warning", "w"),
        ("error", "e"),
    ]


# --- models ------------------------------------------------------------------


def test_a_pipeline_runs_a_model_and_reads_what_it_wrote() -> None:
    runner = PipelineRunner({"image.jpg": b"abc"})
    runner.register_model(HELLO_MODEL, transcribes("<score/>"))

    runner.run(RunsAModel("hello-pipeline", "1.0.0", model=HELLO_MODEL), input=["image.jpg"])

    assert runner.model_calls == [ModelCall(model=HELLO_MODEL, input=["image.jpg"], parameters={})]
    assert runner.log_messages() == ["the model wrote 8 characters"]


def test_one_implementation_registered_twice_pins_two_different_models() -> None:
    """The reason a *Pipeline* is a class: `mzk` and `mzk-dev` in miniature."""
    stable = RunsAModel("hello-pipeline", "1.0.0", model=HELLO_MODEL)
    development = RunsAModel("hello-pipeline-dev", "2.0.0", model=OTHER_MODEL)

    runner = PipelineRunner({"image.jpg": b"abc"})
    runner.register_model(HELLO_MODEL, transcribes("<stable/>"))
    runner.register_model(OTHER_MODEL, transcribes("<development/>"))

    runner.run(stable, input=["image.jpg"])
    assert runner.files["transcription.musicxml"] == b"<stable/>"

    runner.run(development, input=["image.jpg"])
    assert runner.files["transcription.musicxml"] == b"<development/>"

    assert [call.model for call in runner.model_calls] == [HELLO_MODEL, OTHER_MODEL]
    assert (stable.description().name, development.description().name) == (
        "hello-pipeline",
        "hello-pipeline-dev",
    )


def test_a_model_that_fails_raises_with_its_reason() -> None:
    def refuses(call: ModelCall, files: dict[str, bytes]) -> None:
        raise RuntimeError("No staves found in the image.")

    runner = PipelineRunner({"image.jpg": b"abc"})
    runner.register_model(HELLO_MODEL, refuses)

    with pytest.raises(ModelExecutionFailed) as failure:
        runner.run(RunsAModel("p", "1.0.0", model=HELLO_MODEL), input=["image.jpg"])

    assert failure.value.model == HELLO_MODEL
    assert "No staves found in the image." in str(failure.value)


def test_running_an_unregistered_model_is_a_fault_in_the_test() -> None:
    # Not a ModelExecutionFailed: a Pipeline reaching for something the test did
    # not think about must not be catchable as an ordinary model failure.
    runner = PipelineRunner({"image.jpg": b"abc"})

    with pytest.raises(UnexpectedModelExecution):
        runner.run(RunsAModel("p", "1.0.0", model=HELLO_MODEL), input=["image.jpg"])


def test_models_run_concurrently_in_the_ordinary_way() -> None:
    """One `execute_model` per staff under a TaskGroup — the shape a real
    page-level pipeline has."""

    class PerStaff(Pipeline):
        name, version = "per-staff", "1.0.0"
        signature = Signature(input=["Staves/{*s}/image.jpg"])

        async def execute(self, ctx: PipelineContext) -> None:
            async with asyncio.TaskGroup() as group:
                for staff in ctx.input:
                    group.create_task(ctx.execute_model(HELLO_MODEL, input=[staff]))

    runner = PipelineRunner({"Staves/1/image.jpg": b"a", "Staves/2/image.jpg": b"b"})
    runner.register_model(HELLO_MODEL)

    runner.run(PerStaff(), input=["Staves/1/image.jpg", "Staves/2/image.jpg"])

    assert [call.input for call in runner.model_calls] == [
        ["Staves/1/image.jpg"],
        ["Staves/2/image.jpg"],
    ]


def test_execution_parameters_reach_the_pipeline_and_the_model() -> None:
    """The *other* kind of parameter: sent by the *User*, per execution."""

    class PassesThem(Pipeline):
        name, version = "passes-them", "1.0.0"
        signature = Signature()

        async def execute(self, ctx: PipelineContext) -> None:
            await ctx.execute_model(HELLO_MODEL, parameters={"threshold": ctx.parameters["t"]})

    runner = PipelineRunner()
    runner.register_model(HELLO_MODEL)

    runner.run(PassesThem(), parameters={"t": 0.4})

    assert runner.model_calls[0].parameters == {"threshold": 0.4}


# --- declaring a pipeline ----------------------------------------------------


def test_a_pipeline_describes_itself_for_discovery() -> None:
    description = Doubling().description()

    assert (description.name, description.version) == ("doubling", "1.0.0")
    assert description.signature.output == ["doubled.bin"]


def test_a_pipeline_that_does_not_say_what_it_is_cannot_be_announced() -> None:
    class Nameless(Pipeline):
        async def execute(self, ctx: PipelineContext) -> None: ...

    with pytest.raises(InvalidPipeline) as failure:
        Nameless().description()

    assert "name, version, signature" in str(failure.value)


def test_the_runner_refuses_an_input_list_the_signature_would_not_admit() -> None:
    # The check the `api` service makes before dispatching, so that a test
    # cannot hand a Pipeline a list a User could never send.
    runner = PipelineRunner({"layout.json": b"{}"})

    with pytest.raises(SignatureMismatch):
        runner.run(Doubling(), input=["layout.json"])
