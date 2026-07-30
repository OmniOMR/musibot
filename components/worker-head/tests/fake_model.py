"""A *Model* that exists only to be driven by the tests.

Launched as a real subprocess over real pipes, so the IPC is exercised as
deployed rather than simulated. Its behaviour is steered by environment
variables, which is how one script stands in for a well-behaved model, a broken
one, and a model that dies mid-execution.
"""

import json
import os
import sys
from pathlib import Path

MODE = os.environ.get("FAKE_MODEL_MODE", "ok")

commands = os.fdopen(int(os.environ["MUSIBOT_IPC_COMMAND_FD"]), "r")
results = os.fdopen(int(os.environ["MUSIBOT_IPC_RESULT_FD"]), "w")
pages_dir = Path(os.environ["MUSIBOT_PAGES_DIR"])


def send(message: dict[str, object]) -> None:
    results.write(json.dumps(message) + "\n")
    results.flush()


if MODE == "never-ready":
    # Loads its weights forever, and so is never offered work.
    for _ in commands:
        pass
    sys.exit(0)

if MODE == "wrong-ipc-version":
    send({"type": "ready", "ipc_version": 99, "model": {}})
    sys.exit(0)

if MODE == "spawns-a-child":
    # A model with a worker process of its own — a dataloader, say. The PID is
    # written out before `ready`, so a test can find it the moment the model is
    # up. This mode also ignores `shutdown` below, which is what makes the head
    # escalate to signalling the process group.
    import subprocess

    child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(300)"])
    (pages_dir / "child.pid").write_text(str(child.pid))

send(
    {
        "type": "ready",
        "ipc_version": 1,
        "model": {
            "name": "fake-model",
            "version": "1.0.0",
            "signature": {"input": ["image.jpg"], "output": ["out.txt"]},
            "supports_batching": False,
        },
    }
)

print("fake model started")  # captured by the head as this model's log

for line in commands:
    command = json.loads(line)

    if command["type"] == "shutdown":
        if MODE == "spawns-a-child":
            continue  # deliberately deaf, so the head has to insist
        break

    if command["type"] != "execute":
        continue

    if MODE == "die":
        sys.exit(3)  # dies mid-execution, reporting nothing

    if MODE == "fail":
        send(
            {
                "type": "failed",
                "execution_id": command["execution_id"],
                "error": "No staves found in the image.",
            }
        )
        continue

    page_dir = pages_dir / command["page"]

    if MODE == "wrong-path":
        # Reports success, but writes its output somewhere its signature does
        # not promise — the commonest way to get a Model wrong.
        (page_dir / "typo.txt").write_text("misplaced", encoding="utf-8")
        send({"type": "completed", "execution_id": command["execution_id"]})
        continue

    (page_dir / "out.txt").write_text("produced by the fake model", encoding="utf-8")
    if MODE == "extra-files":
        (page_dir / "warnings.json").write_text("[]", encoding="utf-8")
    send({"type": "completed", "execution_id": command["execution_id"]})
