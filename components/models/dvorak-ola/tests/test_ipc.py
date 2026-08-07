"""The IPC loop, driven over ordinary in-memory streams rather than pipes."""

from __future__ import annotations

import io
import json
from pathlib import Path
from typing import Any

from fake_detector import FakeDetector, a_detection, a_page

from dvorak_ola.detector import DetectionSettings
from dvorak_ola.ipc import INPUT_FILE, MODEL_NAME, MODEL_VERSION, OUTPUT_FILE, run


def drive(
    pages_dir: Path,
    *commands: dict[str, Any],
    detector: FakeDetector | None = None,
) -> list[dict[str, Any]]:
    """Run the model over a scripted command stream and collect what it sent."""
    command_stream = io.StringIO(
        "".join(json.dumps(command) + "\n" for command in commands)
        + json.dumps({"type": "shutdown"})
        + "\n"
    )
    result_stream = io.StringIO()

    run(command_stream, result_stream, pages_dir, detector or FakeDetector())

    return [json.loads(line) for line in result_stream.getvalue().splitlines() if line]


def a_musicorpus_page(pages_dir: Path, page_id: str = "7Kf2mP9xLwQa") -> str:
    page_dir = pages_dir / page_id
    page_dir.mkdir(parents=True)
    (page_dir / INPUT_FILE).write_bytes(b"not-really-a-jpeg")
    return page_id


def an_execution(
    page_id: str,
    execution_id: str = "e7c1",
    input_files: list[str] | None = None,
    parameters: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "type": "execute",
        "execution_id": execution_id,
        "page": page_id,
        "input": input_files if input_files is not None else [INPUT_FILE],
        "parameters": parameters or {},
    }


def test_it_announces_itself_before_anything_else(tmp_path: Path) -> None:
    [ready] = drive(tmp_path)

    assert ready["type"] == "ready"
    assert ready["ipc_version"] == 1
    assert ready["model"]["name"] == MODEL_NAME
    assert ready["model"]["version"] == MODEL_VERSION
    assert ready["model"]["signature"] == {"input": [INPUT_FILE], "output": [OUTPUT_FILE]}
    assert ready["model"]["supports_batching"] is False


def test_the_announced_version_can_be_the_served_checkpoints(tmp_path: Path) -> None:
    # Deploying a different checkpoint must not merge two models into one
    # registry entry, so the version is a deployment's to state.
    result_stream = io.StringIO()
    run(io.StringIO(""), result_stream, tmp_path, FakeDetector(), model_version="3.0-2027-01-01")

    ready = json.loads(result_stream.getvalue())
    assert ready["model"]["version"] == "3.0-2027-01-01"


def test_an_execution_writes_the_layout_and_reports(tmp_path: Path) -> None:
    page_id = a_musicorpus_page(tmp_path)
    detector = FakeDetector(
        a_page(
            [a_detection("staff", y=100), a_detection("system", y=90)],
            image_width=2000,
            image_height=3000,
        )
    )

    _, completed = drive(tmp_path, an_execution(page_id), detector=detector)

    assert completed == {"type": "completed", "execution_id": "e7c1"}

    written = json.loads((tmp_path / page_id / OUTPUT_FILE).read_text(encoding="utf-8"))
    assert written["images"] == [{"id": 0, "width": 2000, "height": 3000, "file_name": INPUT_FILE}]
    assert [annotation["category_id"] for annotation in written["annotations"]] == [0, 3]


def test_it_reads_the_file_the_command_staged(tmp_path: Path) -> None:
    page_id = a_musicorpus_page(tmp_path)
    detector = FakeDetector()

    drive(tmp_path, an_execution(page_id), detector=detector)

    [(image, _)] = detector.calls
    assert image == tmp_path / page_id / INPUT_FILE


def test_a_missing_input_file_fails_that_execution(tmp_path: Path) -> None:
    (tmp_path / "7Kf2mP9xLwQa").mkdir()

    _, failed = drive(tmp_path, an_execution("7Kf2mP9xLwQa"))

    assert failed["type"] == "failed"
    assert failed["execution_id"] == "e7c1"
    assert INPUT_FILE in failed["error"]


def test_parameters_override_the_configured_settings(tmp_path: Path) -> None:
    page_id = a_musicorpus_page(tmp_path)
    detector = FakeDetector(settings=DetectionSettings(confidence=0.25, image_size=640))

    drive(
        tmp_path,
        an_execution(page_id, parameters={"confidence": 0.5, "image_size": 1280}),
        detector=detector,
    )

    [(_, settings)] = detector.calls
    assert settings.confidence == 0.5
    assert settings.image_size == 1280
    # Untouched knobs keep what the deployment configured.
    assert settings.iou == DetectionSettings().iou


def test_an_unusable_parameter_fails_only_that_execution(tmp_path: Path) -> None:
    page_id = a_musicorpus_page(tmp_path)

    _, failed, completed = drive(
        tmp_path,
        an_execution(page_id, "e7c1", parameters={"confidence": 7}),
        an_execution(page_id, "e7c2"),
    )

    assert failed["execution_id"] == "e7c1"
    assert "confidence" in failed["error"]
    assert completed["type"] == "completed"


def test_more_than_one_staged_file_is_refused_legibly(tmp_path: Path) -> None:
    page_id = a_musicorpus_page(tmp_path)

    _, failed = drive(tmp_path, an_execution(page_id, input_files=[INPUT_FILE, "layout.json"]))

    assert failed["type"] == "failed"
    assert "one page image" in failed["error"]


def test_each_execution_is_reported_separately(tmp_path: Path) -> None:
    first = a_musicorpus_page(tmp_path, "7Kf2mP9xLwQa")
    second = a_musicorpus_page(tmp_path, "Qm3vN8xTrb2c")

    _, one, two = drive(tmp_path, an_execution(first, "e7c1"), an_execution(second, "e7c2"))

    assert [one["execution_id"], two["execution_id"]] == ["e7c1", "e7c2"]
    assert (tmp_path / second / OUTPUT_FILE).exists()


def test_an_unknown_command_is_ignored(tmp_path: Path) -> None:
    page_id = a_musicorpus_page(tmp_path)

    # A command from a newer Worker Head must not stop the model, or the
    # protocol could never grow.
    results = drive(tmp_path, {"type": "recalibrate-flux"}, an_execution(page_id))

    assert [result["type"] for result in results] == ["ready", "completed"]


def test_shutdown_ends_the_loop(tmp_path: Path) -> None:
    command_stream = io.StringIO(json.dumps({"type": "shutdown"}) + "\n" + "this is never read\n")

    run(command_stream, io.StringIO(), tmp_path, FakeDetector())

    assert command_stream.readline() == "this is never read\n"
