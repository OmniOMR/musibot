"""The two parts of the detector that are not ultralytics: boxes and knobs."""

from __future__ import annotations

import pytest

from dvorak_ola.detector import DetectionSettings, pixel_box


def test_a_box_is_rounded_outwards() -> None:
    # The specification asks for a box that fully contains its object, so half a
    # pixel of slack is the safe direction to round in.
    assert pixel_box([10.7, 20.2, 300.1, 60.9], 1000, 1000) == (10, 20, 291, 41)


def test_a_box_is_clamped_to_the_image() -> None:
    # A detector is free to place a box slightly off the edge; a consumer of
    # this file should not have to think about a negative coordinate.
    assert pixel_box([-4.0, -2.0, 1010.0, 500.0], 1000, 1000) == (0, 0, 1000, 500)


def test_a_box_entirely_outside_the_image_is_dropped() -> None:
    assert pixel_box([1200.0, 100.0, 1300.0, 200.0], 1000, 1000) is None


def test_settings_are_unchanged_when_a_pipeline_passes_nothing() -> None:
    settings = DetectionSettings(confidence=0.4)

    assert settings.overridden_by({}) == settings


def test_settings_a_pipeline_does_not_mention_are_left_alone() -> None:
    settings = DetectionSettings(confidence=0.4, iou=0.5).overridden_by({"image_size": 1280})

    assert (settings.confidence, settings.iou, settings.image_size) == (0.4, 0.5, 1280)


@pytest.mark.parametrize(
    "parameters",
    [
        {"confidence": 1.5},
        {"confidence": "high"},
        {"confidence": True},
        {"iou": -0.1},
        {"image_size": 0},
        {"image_size": 640.5},
        {"max_detections": "lots"},
    ],
)
def test_an_unusable_parameter_is_refused_by_name(parameters: dict[str, object]) -> None:
    # Parameters come from a Pipeline and nothing has validated them, so a bad
    # one has to become a legible failure rather than a stack trace out of the
    # middle of ultralytics.
    [name] = parameters

    with pytest.raises(ValueError, match=name):
        DetectionSettings().overridden_by(parameters)
