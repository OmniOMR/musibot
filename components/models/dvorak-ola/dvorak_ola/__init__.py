"""A Musibot *Model* that reads the layout of a page of sheet music.

It runs Vojtěch Dvořák's [OMR Layout Analysis](https://github.com/v-dvorak/omr-layout-analysis)
YOLO checkpoint over a page image and writes what it found as a Musicorpus
`layout.json`: staves, systems, grandstaves, and the measures within staves and
systems. It transcribes nothing — locating things is the whole job, and it is
the first half of a page-level recognition pipeline whose second half cuts the
page up along these boxes and hands the crops to a transcription model.

There is deliberately nothing of Musibot in here: no `musibot.core` import, no
messaging, no object storage. A *Model* speaks JSON lines on two file
descriptors and touches files in a directory, which is what lets this one bring
torch and ultralytics without any of it reaching the rest of the system.

The pieces, in the order a page passes through them:

- `cli` — what a *Worker Head* launches; loads the weights before anything else.
- `ipc` — the worker IPC contract: announce, then serve executions one at a time.
- `detector` — the ultralytics model, and the boxes it returns.
- `layout` — those boxes as a Musicorpus `layout.json`.
- `categories` — the translation between the checkpoint's class names and the
  *Musicorpus Specification*'s.
"""

from dvorak_ola.cli import main
from dvorak_ola.ipc import (
    INPUT_FILE,
    IPC_VERSION,
    MODEL_NAME,
    MODEL_VERSION,
    OUTPUT_FILE,
    run,
)

__all__ = [
    "INPUT_FILE",
    "IPC_VERSION",
    "MODEL_NAME",
    "MODEL_VERSION",
    "OUTPUT_FILE",
    "main",
    "run",
]
