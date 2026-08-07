"""The worker IPC contract, as this model implements it.

Nothing of Musibot is imported here and nothing needs to be: the contract is
JSON lines on two file descriptors plus files in a directory. See
`docs/worker-ipc.md` in the Musibot repository, and `hello-model` for the same
loop with no machine learning behind it.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, TextIO

from dvorak_ola.detector import PageDetector
from dvorak_ola.layout import layout_document, summarise

MODEL_NAME = "dvorak-ola"

MODEL_VERSION = "2.0-2025-03-09"
"""The release of the checkpoint this package was written against.

A constant rather than something read off the weights file, because a YOLO
checkpoint carries no identity of its own — and derived from nothing at runtime,
because what a *Pipeline* pinned must not change under it. Serving a different
checkpoint therefore means passing `--model-version` alongside `--weights`; see
the README.
"""

IPC_VERSION = 1

INPUT_FILE = "image.jpg"
OUTPUT_FILE = "layout.json"


def send(results: TextIO, message: dict[str, Any]) -> None:
    """Put one message on the result pipe.

    The flush is not optional: a pipe is block-buffered, so an unflushed message
    is not late but invisible, and the *Worker Head* waits forever.
    """
    results.write(json.dumps(message) + "\n")
    results.flush()


def analyse(detector: PageDetector, page_dir: Path, command: dict[str, Any]) -> None:
    """Do one execution: read the page image, write `layout.json` beside it."""
    input_files = command["input"]
    if len(input_files) != 1:
        raise ValueError(
            f"This model reads one page image, but {len(input_files)} files were staged."
        )
    [image_file] = input_files

    settings = detector.settings.overridden_by(command.get("parameters") or {})
    page = detector.detect(page_dir / image_file, settings)

    print(f"{image_file}: found {summarise(page.detections)}")

    document = layout_document(image_file, page, MODEL_NAME, MODEL_VERSION)
    (page_dir / OUTPUT_FILE).write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")


def run(
    commands: TextIO,
    results: TextIO,
    pages_dir: Path,
    detector: PageDetector,
    model_version: str = MODEL_VERSION,
) -> None:
    """Announce this model, then serve commands until told to stop.

    One command at a time, in a plain loop — a *Model* does not multitask, and
    the *Worker Head* sends nothing further until this one is reported.
    """
    send(
        results,
        {
            "type": "ready",
            "ipc_version": IPC_VERSION,
            "model": {
                "name": MODEL_NAME,
                "version": model_version,
                "signature": {"input": [INPUT_FILE], "output": [OUTPUT_FILE]},
                # A page at a time, and batching left off deliberately. See
                # "Not yet exercised" in the README.
                "supports_batching": False,
            },
        },
    )

    # Iterating the pipe ends at EOF, which is what a Worker Head that died
    # looks like from here — and means the same thing as `shutdown`.
    for line in commands:
        line = line.strip()
        if not line:
            continue

        command = json.loads(line)
        command_type = command.get("type")

        if command_type == "shutdown":
            break

        if command_type != "execute":
            # Unknown types are ignored in both directions, so that the protocol
            # can grow without either side breaking.
            continue

        execution_id = command["execution_id"]
        try:
            analyse(detector, pages_dir / command["page"], command)
        except Exception as exception:  # noqa: BLE001
            # Deliberately blind. Whatever goes wrong — a missing file, a
            # parameter a Pipeline got wrong, torch running out of memory — this
            # execution has to be reported as failed rather than taking the
            # process down with it, and the string reaches a human through the
            # Pipeline Execution log.
            send(
                results,
                {"type": "failed", "execution_id": execution_id, "error": str(exception)},
            )
        else:
            send(results, {"type": "completed", "execution_id": execution_id})
