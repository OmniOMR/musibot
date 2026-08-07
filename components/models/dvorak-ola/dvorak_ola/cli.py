"""What a *Worker Head* actually launches.

The command line is small on purpose. Only two things about this model are
deployment decisions — which checkpoint it serves and what version it therefore
announces — and everything else here is a default that a *Pipeline* can override
per execution through the command's `parameters`.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from dvorak_ola.detector import DetectionSettings, YoloDetector
from dvorak_ola.ipc import MODEL_NAME, MODEL_VERSION, run


def parser() -> argparse.ArgumentParser:
    defaults = DetectionSettings()

    argument_parser = argparse.ArgumentParser(
        prog="musibot-dvorak-ola",
        description=(
            "A Musibot Model that detects the layout of a page of sheet music: "
            "staves, systems, grandstaves and their measures."
        ),
    )
    argument_parser.add_argument(
        "--weights",
        type=Path,
        required=True,
        help="The .pt checkpoint to serve. Downloaded by hand; see the README.",
    )
    argument_parser.add_argument(
        "--model-version",
        default=MODEL_VERSION,
        help=(
            "What to announce as this model's version. Defaults to the release "
            f"this package was written against ({MODEL_VERSION}); pass the matching "
            "one when serving a different checkpoint, or two of them merge into "
            "one entry in the registry."
        ),
    )
    argument_parser.add_argument(
        "--confidence",
        type=float,
        default=defaults.confidence,
        help="Drop detections the model is less sure of than this (default: %(default)s).",
    )
    argument_parser.add_argument(
        "--iou",
        type=float,
        default=defaults.iou,
        help="How much two boxes of one class may overlap (default: %(default)s).",
    )
    argument_parser.add_argument(
        "--image-size",
        type=int,
        default=defaults.image_size,
        help="What the page is scaled to before it is looked at (default: %(default)s).",
    )
    argument_parser.add_argument(
        "--max-detections",
        type=int,
        default=defaults.max_detections,
        help="Ceiling on the objects one page may have (default: %(default)s).",
    )
    argument_parser.add_argument(
        "--device",
        default=None,
        help="What torch runs on — 'cpu', '0', 'cuda:0'. Chosen automatically when unset.",
    )
    return argument_parser


def main() -> None:
    """Load the weights, then open the descriptors and serve."""
    arguments = parser().parse_args()

    if not arguments.weights.is_file():
        # Checked here rather than left to ultralytics, which would treat an
        # unknown name as something to fetch from the internet and fail with a
        # download error. The weights are put in place by whoever deploys this;
        # the Model is given nothing writable but its pages directory.
        sys.exit(f"error: no checkpoint at {arguments.weights}")

    # Ultralytics will pip-install what it thinks is missing, mid-run, into
    # whatever environment it finds itself in. A deployed Worker's virtual
    # environment is not a thing to mutate from inside an execution.
    os.environ.setdefault("YOLO_AUTOINSTALL", "false")

    # Goes to stdout, which the Worker Head captures as this model's log.
    print(f"{MODEL_NAME} {arguments.model_version} loading {arguments.weights.name}")

    detector = YoloDetector(
        weights=arguments.weights,
        settings=DetectionSettings(
            confidence=arguments.confidence,
            iou=arguments.iou,
            image_size=arguments.image_size,
            max_detections=arguments.max_detections,
        ),
        device=arguments.device,
    )

    print(f"{MODEL_NAME} {arguments.model_version} ready")

    # Opened only now: the weights are loaded first, so that the Worker Head is
    # told `ready` when this model genuinely is, and is offered no work before.
    commands = os.fdopen(int(os.environ["MUSIBOT_IPC_COMMAND_FD"]), "r")
    results = os.fdopen(int(os.environ["MUSIBOT_IPC_RESULT_FD"]), "w")
    pages_dir = Path(os.environ["MUSIBOT_PAGES_DIR"])

    run(commands, results, pages_dir, detector, model_version=arguments.model_version)
