"""Driving a real *Model* subprocess over real pipes.

These use an actual child process rather than fake streams, because the parts
worth testing here — descriptor passing, flushing, EOF, a process that dies —
are exactly the parts that in-memory streams would not have.
"""

import asyncio
import os
import sys
from collections.abc import Callable, Coroutine
from pathlib import Path
from typing import Any, TypeVar

import pytest

from musibot.worker_head.model_process import ModelFailed, ModelProcess, ModelProtocolError

FAKE_MODEL = Path(__file__).parent / "fake_model.py"

T = TypeVar("T")


def run(scenario: Callable[[], Coroutine[Any, Any, T]]) -> T:
    return asyncio.run(scenario())


def a_model(pages_dir: Path, mode: str = "ok", **kwargs: Any) -> ModelProcess:
    # The mode travels through the environment, which the head passes on to the
    # child along with the descriptor numbers.
    os.environ["FAKE_MODEL_MODE"] = mode
    return ModelProcess(f"{sys.executable} {FAKE_MODEL}", pages_dir, **kwargs)


def test_it_learns_what_the_model_is(tmp_path: Path) -> None:
    async def scenario() -> None:
        model = a_model(tmp_path)
        try:
            description = await model.ensure_running()

            assert description.name == "fake-model"
            assert description.version == "1.0.0"
            assert description.signature.input == ["image.jpg"]
            assert description.supports_batching is False
        finally:
            await model.shutdown()

    run(scenario)


def test_an_execution_runs_and_the_model_writes_its_output(tmp_path: Path) -> None:
    async def scenario() -> None:
        page_dir = tmp_path / "7Kf2mP9xLwQa"
        page_dir.mkdir()
        model = a_model(tmp_path)
        try:
            await model.execute("e7c1", "7Kf2mP9xLwQa", ["image.jpg"], {})

            assert (page_dir / "out.txt").read_text(encoding="utf-8") == (
                "produced by the fake model"
            )
        finally:
            await model.shutdown()

    run(scenario)


def test_the_model_stays_up_across_executions(tmp_path: Path) -> None:
    async def scenario() -> None:
        for page_id in ("7Kf2mP9xLwQa", "Qm3vN8xTrb2c"):
            (tmp_path / page_id).mkdir()

        model = a_model(tmp_path)
        try:
            await model.execute("e7c1", "7Kf2mP9xLwQa", [], {})
            first = model._process
            await model.execute("e7c2", "Qm3vN8xTrb2c", [], {})

            # Starting a model can cost gigabytes of weights, so it is started
            # once and kept, never restarted per execution.
            assert model._process is first
        finally:
            await model.shutdown()

    run(scenario)


def test_a_reported_failure_carries_its_error(tmp_path: Path) -> None:
    async def scenario() -> None:
        (tmp_path / "7Kf2mP9xLwQa").mkdir()
        model = a_model(tmp_path, mode="fail")
        try:
            with pytest.raises(ModelFailed, match="No staves found"):
                await model.execute("e7c1", "7Kf2mP9xLwQa", [], {})
        finally:
            await model.shutdown()

    run(scenario)


def test_a_model_that_dies_fails_the_execution_in_flight(tmp_path: Path) -> None:
    async def scenario() -> None:
        (tmp_path / "7Kf2mP9xLwQa").mkdir()
        model = a_model(tmp_path, mode="die")
        try:
            with pytest.raises(ModelFailed, match="exited without reporting"):
                await model.execute("e7c1", "7Kf2mP9xLwQa", [], {})
        finally:
            await model.shutdown()

    run(scenario)


def test_a_dead_model_is_restarted_for_the_next_execution(tmp_path: Path) -> None:
    async def scenario() -> None:
        (tmp_path / "7Kf2mP9xLwQa").mkdir()
        model = a_model(tmp_path, mode="die")
        try:
            with pytest.raises(ModelFailed):
                await model.execute("e7c1", "7Kf2mP9xLwQa", [], {})
            assert not model.is_running

            # The next execution brings it back up rather than failing forever.
            os.environ["FAKE_MODEL_MODE"] = "ok"
            await model.execute("e7c2", "7Kf2mP9xLwQa", [], {})

            assert (tmp_path / "7Kf2mP9xLwQa" / "out.txt").exists()
        finally:
            await model.shutdown()

    run(scenario)


def test_a_model_speaking_another_ipc_version_is_refused(tmp_path: Path) -> None:
    async def scenario() -> None:
        model = a_model(tmp_path, mode="wrong-ipc-version")
        try:
            with pytest.raises(ModelProtocolError, match="IPC version"):
                await model.ensure_running()
        finally:
            await model.shutdown()

    run(scenario)


def test_a_model_that_never_becomes_ready_times_out(tmp_path: Path) -> None:
    async def scenario() -> None:
        model = a_model(tmp_path, mode="never-ready", ready_timeout_seconds=0.3)
        try:
            with pytest.raises(ModelProtocolError, match="ready"):
                await model.ensure_running()
        finally:
            await model.shutdown()

    run(scenario)


def test_shutdown_stops_the_model(tmp_path: Path) -> None:
    async def scenario() -> None:
        model = a_model(tmp_path)
        await model.ensure_running()

        await model.shutdown()

        assert not model.is_running

    run(scenario)
