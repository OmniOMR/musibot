"""`SlicePipelineV1`: a page and its layout in, one crop per staff out."""

import cv2
import numpy as np
import pytest
from musibot.orchestrator_head.testing import PipelineRunner

from pmcg_orchestrator.page_from_staff import PageFromStaffPipelineV1, PageFromStaffPipelineV2
from pmcg_orchestrator.slice import SlicePipelineV1
from tests.fakes import LAYOUT_MODEL, STAFF_MODEL, a_layout, a_page, a_runner

# Two staves side by side at the same height, and one below them, listed out of
# reading order on purpose.
STAVES = ((220, 200, 100, 30), (20, 40, 150, 30), (220, 40, 150, 30))


def a_pipeline() -> SlicePipelineV1:
    return SlicePipelineV1("pmcg-slice", "1")


def a_slicing_runner(*staves: tuple[int, int, int, int]) -> PipelineRunner:
    return PipelineRunner({"image.jpg": a_page(), "layout.json": a_layout(*staves)})


def test_it_cuts_a_crop_per_staff_and_runs_no_model() -> None:
    runner = a_slicing_runner(*STAVES)

    runner.run(a_pipeline(), input=["image.jpg", "layout.json"])

    assert runner.model_calls == []
    assert runner.written == ["Staves/1/image.jpg", "Staves/2/image.jpg", "Staves/3/image.jpg"]


@pytest.mark.parametrize("page_pipeline", [PageFromStaffPipelineV1, PageFromStaffPipelineV2])
def test_its_crops_are_exactly_the_ones_mzk_page_cuts(page_pipeline: type) -> None:
    """Same numbering, same margin, same bytes — which is what lets a User run
    the steps of `mzk-page` by hand and get the page `mzk-page` would have."""
    page = a_runner(*STAVES)
    page.run(
        page_pipeline("mzk-page", "x", layout_model=LAYOUT_MODEL, staff_model=STAFF_MODEL),
        input=["image.jpg"],
    )

    sliced = a_slicing_runner(*STAVES)
    sliced.run(a_pipeline(), input=["image.jpg", "layout.json"])

    for number in (1, 2, 3):
        crop = f"Staves/{number}/image.jpg"
        assert sliced.files[crop] == page.files[crop]


def test_staves_are_numbered_in_reading_order() -> None:
    """Top to bottom, then left to right between staves at the same height."""
    runner = a_slicing_runner(*STAVES)

    runner.run(a_pipeline(), input=["image.jpg", "layout.json"])

    sizes = [_size(runner.files[f"Staves/{n}/image.jpg"]) for n in (1, 2, 3)]
    # A 30px staff gets a 27px margin; the one at the left edge is clamped.
    assert sizes == [(197, 84), (204, 84), (154, 84)]
    assert runner.log_messages() == [
        "Reading the staves out of layout.json ...",
        "Found 3 staves.",
        "Slicing the page into 3 staff images ...",
        "Done.",
    ]


def test_a_layout_with_no_staves_says_so() -> None:
    runner = a_slicing_runner()

    with pytest.raises(ValueError, match="No staves were found"):
        runner.run(a_pipeline(), input=["image.jpg", "layout.json"])


def test_a_layout_that_is_not_json_is_reported_legibly() -> None:
    runner = PipelineRunner({"image.jpg": a_page(), "layout.json": b"not json"})

    with pytest.raises(ValueError, match="layout.json on this page is not JSON"):
        runner.run(a_pipeline(), input=["image.jpg", "layout.json"])


def test_it_declares_a_page_and_its_layout_in_and_crops_out() -> None:
    signature = a_pipeline().description().signature

    assert signature.input == ["image.jpg", "layout.json"]
    assert signature.output == ["Staves/{*}/image.jpg"]


def _size(jpeg: bytes) -> tuple[int, int]:
    image = cv2.imdecode(np.frombuffer(jpeg, dtype=np.uint8), cv2.IMREAD_COLOR)
    assert image is not None, "a crop that is not an image"
    height, width = image.shape[:2]
    return width, height
