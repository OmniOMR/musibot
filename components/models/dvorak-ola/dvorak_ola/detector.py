"""The YOLO checkpoint, and what comes out of it.

Everything that knows about ultralytics is in this file, and it is the only part
of the model that cannot be exercised without torch installed. The rest — the
COCO document and the IPC loop — works against the small dataclasses declared
here, which is what lets the tests drive a whole execution with a fake detector.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, replace
from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol, cast

from dvorak_ola.categories import MUSICORPUS_CATEGORY

if TYPE_CHECKING:
    from ultralytics.engine.results import Results


@dataclass(frozen=True)
class Detection:
    """One found object, in the pixel coordinates of the page image."""

    category: str
    """A *Musicorpus* category name — `staff`, `systemMeasure` and so on."""

    x: int
    y: int
    width: int
    height: int

    score: float
    """How sure the model is, between 0 and 1."""


@dataclass(frozen=True)
class PageDetections:
    """Everything found on one page image, and the size of that image.

    The size travels with the detections because the COCO document needs it and
    the detector already has it — going back to the file to measure it again
    would be a second way for the two to disagree.
    """

    image_width: int
    image_height: int
    detections: list[Detection]


@dataclass(frozen=True)
class DetectionSettings:
    """The knobs, either as configured at startup or as a *Pipeline* set them."""

    confidence: float = 0.25
    """Detections the model is less sure of than this are dropped."""

    iou: float = 0.7
    """How much two boxes of one class may overlap before the weaker is dropped."""

    image_size: int = 640
    """What the page is scaled to before it is looked at.

    The checkpoint was trained at 640, so that is the honest default, and it is
    also where the model behaves as its author measured it. A page scan is many
    times that, and the things scaled away are the small ones — a `staffMeasure`
    on a dense page far sooner than a `system` — so a *Pipeline* that cares
    about measures more than about throughput has a reason to raise it.
    """

    max_detections: int = 1000
    """A ceiling on how many objects one page may have.

    Raised well above ultralytics' own default of 300, which a page of dense
    orchestral music passes on measures alone — the training data averages
    around seventy objects per page and the busy pages are several times that.
    Hitting the ceiling is silent: the surplus is simply not returned, so the
    number is set where reaching it means something has gone wrong rather than
    where it merely bites.
    """

    def overridden_by(self, parameters: dict[str, Any]) -> DetectionSettings:
        """Apply one execution's `parameters`, refusing anything unusable.

        A *Pipeline* passes these through untouched and nothing has validated
        them, so a bad value must become a legible failure for that execution
        rather than a stack trace out of the middle of ultralytics.
        """
        settings = self

        if "confidence" in parameters:
            settings = replace(
                settings, confidence=_fraction(parameters["confidence"], "confidence")
            )
        if "iou" in parameters:
            settings = replace(settings, iou=_fraction(parameters["iou"], "iou"))
        if "image_size" in parameters:
            settings = replace(
                settings, image_size=_positive_int(parameters["image_size"], "image_size")
            )
        if "max_detections" in parameters:
            settings = replace(
                settings,
                max_detections=_positive_int(parameters["max_detections"], "max_detections"),
            )

        return settings


def _fraction(value: Any, name: str) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool) or not 0 <= value <= 1:
        raise ValueError(f"Parameter '{name}' must be a number between 0 and 1, got {value!r}.")
    return float(value)


def _positive_int(value: Any, name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise ValueError(f"Parameter '{name}' must be a positive whole number, got {value!r}.")
    return value


class PageDetector(Protocol):
    """What the IPC loop needs of a detector, and no more.

    Declared so that a test can hand `run` something that returns fixed boxes,
    and so that the loop's dependency on torch is a matter of what `main` builds
    rather than of what the loop imports.
    """

    settings: DetectionSettings

    def detect(self, image: Path, settings: DetectionSettings) -> PageDetections: ...


class YoloDetector:
    """The real one: an ultralytics model, loaded once and kept."""

    def __init__(
        self,
        weights: Path,
        settings: DetectionSettings,
        device: str | None = None,
    ) -> None:
        # Imported here rather than at module scope so that the COCO document
        # and the IPC loop can be tested without torch in the environment. It
        # still happens at startup — before `ready`, which is the rule that
        # matters, since a Worker must not be offered work it cannot yet do.
        from ultralytics import YOLO

        self.settings = settings
        self._device = device
        self._model = YOLO(str(weights))

        # `names` is written into the checkpoint at training time, so this is
        # the model telling us what it predicts rather than us assuming it. A
        # class we have no Musicorpus name for is dropped rather than refused:
        # a later checkpoint that adds one should still be servable, and the
        # warning is what makes the omission something a human sees.
        self._names: dict[int, str] = dict(self._model.names)
        unmapped = sorted(set(self._names.values()) - set(MUSICORPUS_CATEGORY))
        if unmapped:
            print(
                f"warning: the checkpoint predicts {', '.join(unmapped)}, which this model "
                f"has no Musicorpus category for — those detections will be dropped"
            )

    def detect(self, image: Path, settings: DetectionSettings) -> PageDetections:
        """Run the whole page through the model in one go."""
        # The cast is because `predict` is also the entry point to ultralytics'
        # `embed=` mode, which returns raw tensors instead of results. Unstreamed
        # and unembedded, as here, it returns one `Results` per source image.
        [result] = cast(
            "list[Results]",
            self._model.predict(
                source=str(image),
                conf=settings.confidence,
                iou=settings.iou,
                imgsz=settings.image_size,
                max_det=settings.max_detections,
                device=self._device,
                verbose=False,
            ),
        )

        height, width = result.orig_shape
        boxes = result.boxes
        if boxes is None:
            # A segmentation or pose checkpoint put where a detection one was
            # meant. Nothing else about this model would notice.
            raise RuntimeError("The checkpoint returned no boxes; it is not a detection model.")

        detections = []
        for corners, class_index, score in zip(
            boxes.xyxy.tolist(), boxes.cls.tolist(), boxes.conf.tolist()
        ):
            category = MUSICORPUS_CATEGORY.get(self._names.get(int(class_index), ""))
            if category is None:
                continue
            box = pixel_box(corners, width, height)
            if box is None:
                continue
            x, y, box_width, box_height = box
            detections.append(
                Detection(
                    category=category,
                    x=x,
                    y=y,
                    width=box_width,
                    height=box_height,
                    score=round(float(score), 4),
                )
            )

        return PageDetections(image_width=width, image_height=height, detections=detections)


def pixel_box(
    corners: list[float], image_width: int, image_height: int
) -> tuple[int, int, int, int] | None:
    """Turn one `xyxy` box into the integer `[x, y, width, height]` COCO wants.

    Rounded outwards, because the specification asks for a box that fully
    contains its object and half a pixel of slack is cheaper than a clipped
    staff line. Clamped to the image, because a detector is free to place a box
    slightly off the edge and a negative coordinate is not something a consumer
    of this file should have to think about.

    A box left with no area by that clamping — entirely outside the image, which
    would be strange but is not impossible — is dropped, since it locates
    nothing.
    """
    left, top, right, bottom = corners

    x = max(0, math.floor(left))
    y = max(0, math.floor(top))
    far_x = min(image_width, math.ceil(right))
    far_y = min(image_height, math.ceil(bottom))

    if far_x <= x or far_y <= y:
        return None

    return x, y, far_x - x, far_y - y
