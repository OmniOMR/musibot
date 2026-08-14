"""Cutting a page image into one crop per staff.

Deliberately the simplest thing that can work: each staff is the box the layout
model reported, grown by a margin, clamped to the page. No deskewing, no
straightening, no attempt to normalise the staff height — a transcription model
that wants any of that should say so, and then it belongs here as a step of its
own rather than smuggled into the crop.

This is the piece most likely to move out of this repository one day. It is
*Musicorpus* logic rather than *Musibot* logic — turning a page and its layout
into subdivision crops is true of the format, not of this deployment — and the
[musicorpus](https://github.com/OmniOMR/musicorpus) package is where it will go
when it has somewhere to land. Until then this is the only *Pipeline* that
slices, so it is developed here.

Every function here is blocking CPU work, so callers run them off the event
loop.
"""

import cv2
import numpy as np

from omniomr_orchestrator.layout import StaffBox

JPEG_QUALITY = 95
"""What a staff crop is re-encoded at. High, because this image is a *Model's*
input rather than something a person looks at, and JPEG artefacts around staff
lines are exactly the kind of damage a recogniser notices."""


class UnreadableImage(ValueError):
    """The page image is not one OpenCV can decode."""


def decode_page(data: bytes) -> np.ndarray:
    """Decode the page scan, keeping whatever colour it came in."""
    image = cv2.imdecode(np.frombuffer(data, dtype=np.uint8), cv2.IMREAD_COLOR)

    if image is None:
        raise UnreadableImage(
            "The page image could not be decoded; it may not be a JPEG or PNG at all"
        )

    return image


def crop_staff(page: np.ndarray, box: StaffBox, padding_ratio: float) -> np.ndarray:
    """One staff, with a margin proportional to its own height.

    Proportional rather than a fixed number of pixels so that the same
    *Pipeline* behaves the same way on a 300dpi scan and a 600dpi one: the
    margin is a fraction of the staff, which is the thing whose size the
    resolution changes.
    """
    height, width = page.shape[:2]
    margin = round(box.height * padding_ratio)

    left = max(0, box.x - margin)
    top = max(0, box.y - margin)
    right = min(width, box.right + margin)
    bottom = min(height, box.bottom + margin)

    if right <= left or bottom <= top:
        # A box wholly outside the image it was detected in. Nothing sensible
        # can be cut here, and an empty array would fail inside the encoder
        # with something far less legible.
        raise UnreadableImage(
            f"A staff at ({box.x}, {box.y}) {box.width}x{box.height} does not overlap "
            f"the {width}x{height} page it was found on"
        )

    return page[top:bottom, left:right]


def encode_jpeg(image: np.ndarray) -> bytes:
    """Encode a crop for a *Model* to read out of the page."""
    written, buffer = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY])

    if not written:
        raise UnreadableImage("A staff crop could not be encoded as JPEG")

    return bytes(buffer)


def slice_page(page_image: bytes, boxes: list[StaffBox], padding_ratio: float) -> list[bytes]:
    """Cut the whole page into staff crops, in the order the boxes are given.

    One call rather than one per staff, so that a caller spends a single hop off
    the event loop on the whole page and decodes the scan once.
    """
    page = decode_page(page_image)
    return [encode_jpeg(crop_staff(page, box, padding_ratio)) for box in boxes]
