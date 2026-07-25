"""A *Model* that transcribes nothing and proves the plumbing works.

It is the reference implementation of the worker IPC contract (see
`docs/worker-ipc.md`): it reads `image.jpg` out of the page folder, writes a
`transcription.musicxml` naming the size of what it read, and reports. Reading
the input is the point — it is what shows the *File* travelled from the *User*
through MinIO and into the *Worker Head's* local mirror before the *Model* ran.

There is deliberately nothing of Musibot in here: no `musibot.core` import, no
messaging, no object storage, and no dependencies at all. A *Model* speaks JSON
lines on two file descriptors and touches files in a directory; everything else
is somebody else's problem, which is what lets a *Model* bring its own python
and its own dependencies.
"""

import json
import os
import sys
from pathlib import Path
from typing import Any, TextIO

MODEL_NAME = "hello-model"
MODEL_VERSION = "1.0.0"

IPC_VERSION = 1

INPUT_FILE = "image.jpg"
OUTPUT_FILE = "transcription.musicxml"


def musicxml(image_bytes: int) -> str:
    """A one-measure score whose lyric reports what the model was given.

    Well-formed MusicXML, so that whatever a *User* opens it with does not
    complain — but musically it is one whole rest and says nothing about the
    page it came from.
    """
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<score-partwise version="4.0">
  <part-list>
    <score-part id="P1">
      <part-name>Piano</part-name>
    </score-part>
  </part-list>
  <part id="P1">
    <measure number="1">
      <attributes>
        <divisions>1</divisions>
        <clef>
          <sign>G</sign>
          <line>2</line>
        </clef>
      </attributes>
      <note>
        <rest measure="yes"/>
        <duration>4</duration>
        <voice>1</voice>
        <type>whole</type>
        <lyric number="1">
          <text>Hello World! ({image_bytes} bytes)</text>
        </lyric>
      </note>
    </measure>
  </part>
</score-partwise>
"""


def transcribe(page_dir: Path) -> None:
    """Read the page's image and write its transcription beside it."""
    image = (page_dir / INPUT_FILE).read_bytes()
    print(f"read {INPUT_FILE} ({len(image)} bytes)")

    (page_dir / OUTPUT_FILE).write_text(musicxml(len(image)), encoding="utf-8")
    print(f"wrote {OUTPUT_FILE}")


def send(results: TextIO, message: dict[str, Any]) -> None:
    """Put one message on the result pipe.

    The flush is not optional: a pipe is block-buffered, so an unflushed message
    is not late but invisible, and the *Worker Head* waits forever.
    """
    results.write(json.dumps(message) + "\n")
    results.flush()


def run(commands: TextIO, results: TextIO, pages_dir: Path) -> None:
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
                "version": MODEL_VERSION,
                "signature": {"input": [INPUT_FILE], "output": [OUTPUT_FILE]},
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
            transcribe(pages_dir / command["page"])
        except Exception as exception:  # noqa: BLE001 — see below
            # Deliberately blind: whatever goes wrong, this execution has to be
            # reported as failed rather than taking the process down with it. A
            # Model that dies fails its work anyway, but reports nothing useful,
            # whereas this error string reaches the Pipeline Execution log and
            # so is worth writing for a human.
            send(
                results,
                {"type": "failed", "execution_id": execution_id, "error": str(exception)},
            )
        else:
            send(results, {"type": "completed", "execution_id": execution_id})


def main() -> None:
    """Open the descriptors the *Worker Head* handed over, and serve."""
    commands = os.fdopen(int(os.environ["MUSIBOT_IPC_COMMAND_FD"]), "r")
    results = os.fdopen(int(os.environ["MUSIBOT_IPC_RESULT_FD"]), "w")
    pages_dir = Path(os.environ["MUSIBOT_PAGES_DIR"])

    # Goes to stdout, which the Worker Head captures as this model's log — the
    # protocol itself is elsewhere, so printing is free.
    print(f"{MODEL_NAME} {MODEL_VERSION} starting", file=sys.stdout)

    run(commands, results, pages_dir)
