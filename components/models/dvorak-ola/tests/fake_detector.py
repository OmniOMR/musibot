"""A detector that finds whatever a test says it finds.

The seam is `PageDetector`, so everything but the ultralytics call itself — the
IPC exchange, the COCO document, the parameter handling — can be driven without
torch in the environment and without a page image to run it on.
"""

from __future__ import annotations

from pathlib import Path

from dvorak_ola.detector import Detection, DetectionSettings, PageDetections


class FakeDetector:
    def __init__(
        self,
        page: PageDetections | None = None,
        settings: DetectionSettings | None = None,
    ) -> None:
        self.settings = settings or DetectionSettings()
        self.page = page or a_page()
        self.calls: list[tuple[Path, DetectionSettings]] = []

    def detect(self, image: Path, settings: DetectionSettings) -> PageDetections:
        # The Worker Head stages the input file before it sends the command, so
        # a Model may simply read it — and a missing one is a failure this Model
        # reports rather than an assumption it makes.
        if not image.is_file():
            raise FileNotFoundError(f"{image.name} is missing")

        self.calls.append((image, settings))
        return self.page


def a_detection(
    category: str = "staff",
    x: int = 10,
    y: int = 20,
    width: int = 300,
    height: int = 40,
    score: float = 0.9,
) -> Detection:
    return Detection(category=category, x=x, y=y, width=width, height=height, score=score)


def a_page(
    detections: list[Detection] | None = None,
    image_width: int = 1000,
    image_height: int = 1400,
) -> PageDetections:
    return PageDetections(
        image_width=image_width,
        image_height=image_height,
        detections=[a_detection()] if detections is None else detections,
    )
