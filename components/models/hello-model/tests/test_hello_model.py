"""The IPC loop, driven over ordinary in-memory streams rather than pipes."""

import io
import json
from pathlib import Path
from typing import Any

from hello_model import INPUT_FILE, MODEL_NAME, MODEL_VERSION, OUTPUT_FILE, run


def drive(pages_dir: Path, *commands: dict[str, Any]) -> list[dict[str, Any]]:
    """Run the model over a scripted command stream and collect what it sent."""
    command_stream = io.StringIO(
        "".join(json.dumps(command) + "\n" for command in commands)
        + json.dumps({"type": "shutdown"})
        + "\n"
    )
    result_stream = io.StringIO()

    run(command_stream, result_stream, pages_dir)

    return [json.loads(line) for line in result_stream.getvalue().splitlines() if line]


def a_page(
    pages_dir: Path, page_id: str = "7Kf2mP9xLwQa", image: bytes = b"not-really-a-jpeg"
) -> str:
    page_dir = pages_dir / page_id
    page_dir.mkdir(parents=True)
    (page_dir / INPUT_FILE).write_bytes(image)
    return page_id


def an_execution(page_id: str, execution_id: str = "e7c1") -> dict[str, Any]:
    return {
        "type": "execute",
        "execution_id": execution_id,
        "page": page_id,
        "input": [INPUT_FILE],
        "parameters": {},
    }


def test_it_announces_itself_before_anything_else(tmp_path: Path) -> None:
    [ready] = drive(tmp_path)

    assert ready["type"] == "ready"
    assert ready["ipc_version"] == 1
    assert ready["model"]["name"] == MODEL_NAME
    assert ready["model"]["version"] == MODEL_VERSION
    assert ready["model"]["signature"] == {"input": [INPUT_FILE], "output": [OUTPUT_FILE]}
    assert ready["model"]["supports_batching"] is False


def test_an_execution_writes_the_transcription_and_reports(tmp_path: Path) -> None:
    page_id = a_page(tmp_path, image=b"0123456789")

    _, completed = drive(tmp_path, an_execution(page_id))

    assert completed == {"type": "completed", "execution_id": "e7c1"}

    written = (tmp_path / page_id / OUTPUT_FILE).read_text(encoding="utf-8")
    assert written.startswith('<?xml version="1.0"')
    # The size it read, which is what shows the input file actually arrived.
    assert "10 bytes" in written


def test_a_missing_input_file_fails_that_execution(tmp_path: Path) -> None:
    (tmp_path / "7Kf2mP9xLwQa").mkdir()

    _, failed = drive(tmp_path, an_execution("7Kf2mP9xLwQa"))

    assert failed["type"] == "failed"
    assert failed["execution_id"] == "e7c1"
    assert INPUT_FILE in failed["error"]


def test_each_execution_is_reported_separately(tmp_path: Path) -> None:
    first = a_page(tmp_path, "7Kf2mP9xLwQa")
    second = a_page(tmp_path, "Qm3vN8xTrb2c")

    _, one, two = drive(tmp_path, an_execution(first, "e7c1"), an_execution(second, "e7c2"))

    assert [one["execution_id"], two["execution_id"]] == ["e7c1", "e7c2"]
    assert (tmp_path / second / OUTPUT_FILE).exists()


def test_an_unknown_command_is_ignored(tmp_path: Path) -> None:
    page_id = a_page(tmp_path)

    # A command from a newer Worker Head must not stop the model, or the
    # protocol could never grow.
    results = drive(tmp_path, {"type": "recalibrate-flux"}, an_execution(page_id))

    assert [result["type"] for result in results] == ["ready", "completed"]


def test_shutdown_ends_the_loop(tmp_path: Path) -> None:
    command_stream = io.StringIO(json.dumps({"type": "shutdown"}) + "\n" + "this is never read\n")
    result_stream = io.StringIO()

    run(command_stream, result_stream, tmp_path)

    assert command_stream.readline() == "this is never read\n"
