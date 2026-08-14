"""The hello pipeline, run the way a *Pipeline* author runs one.

No broker, no object storage and no *Model* — `PipelineRunner` stands in for all
three, so these are ordinary synchronous tests over ordinary python.
"""

import json
from io import BytesIO
from typing import Any

import pytest
from musibot.orchestrator_head import ModelExecutionFailed, NameAndVersion
from musibot.orchestrator_head.testing import ModelCall, PipelineRunner
from PIL import Image

from hello_orchestrator import HelloPipeline
from hello_orchestrator.pipeline import byte_count, layout_document

HELLO_MODEL = NameAndVersion(name="hello-model", version="1.0.0")


def a_jpeg(width: int = 100, height: int = 60) -> bytes:
    buffer = BytesIO()
    Image.new("RGB", (width, height), "white").save(buffer, format="JPEG")
    return buffer.getvalue()


def musicxml(image_bytes: int) -> str:
    """What `hello-model` 1.0.0 writes, in the shape it writes it."""
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<score-partwise version="4.0">
  <part id="P1">
    <measure number="1">
      <note>
        <rest measure="yes"/>
        <lyric number="1">
          <text>Hello World! ({image_bytes} bytes)</text>
        </lyric>
      </note>
    </measure>
  </part>
</score-partwise>
"""


def hello_model(call: ModelCall, files: dict[str, bytes]) -> None:
    """`hello-model` itself: it reads `image.jpg` and reports its size."""
    files["transcription.musicxml"] = musicxml(len(files["image.jpg"])).encode("utf-8")


def a_runner(**overrides: Any) -> PipelineRunner:
    runner = PipelineRunner({"image.jpg": a_jpeg(**overrides)})
    runner.register_model(HELLO_MODEL, hello_model)
    return runner


def a_pipeline(margin: int = 20) -> HelloPipeline:
    return HelloPipeline("hello-pipeline", "1.0.0", model=HELLO_MODEL, margin=margin)


def test_it_runs_the_model_it_was_pinned_to() -> None:
    runner = a_runner()

    runner.run(a_pipeline(), input=["image.jpg"])

    assert runner.model_calls == [ModelCall(model=HELLO_MODEL, input=["image.jpg"], parameters={})]


def test_it_reports_what_the_model_read() -> None:
    """The demonstration that a *Pipeline* can read a *Model's* output.

    The number is one only the *Model* could have known — it is the size of the
    image the *Model* was handed.
    """
    runner = a_runner()

    runner.run(a_pipeline(), input=["image.jpg"])

    assert f"The model read {len(runner.files['image.jpg'])} bytes of image.jpg" in (
        runner.log_messages()
    )


def test_it_writes_a_layout_with_one_inset_staff() -> None:
    runner = a_runner(width=100, height=60)

    runner.run(a_pipeline(margin=20), input=["image.jpg"])

    layout = json.loads(runner.files["layout.json"])
    [annotation] = layout["annotations"]
    assert annotation["bbox"] == [20, 20, 60, 20]
    assert layout["images"][0] == {
        "id": 0,
        "width": 100,
        "height": 60,
        "file_name": "image.jpg",
    }
    assert layout["categories"] == [{"id": 0, "name": "staff"}]


def test_the_margin_is_a_registration_parameter() -> None:
    runner = a_runner(width=100, height=60)

    runner.run(a_pipeline(margin=5), input=["image.jpg"])

    assert json.loads(runner.files["layout.json"])["annotations"][0]["bbox"] == [5, 5, 90, 50]


def test_the_files_it_writes_are_announced() -> None:
    runner = a_runner()

    runner.run(a_pipeline(), input=["image.jpg"])

    # `transcription.musicxml` is the *Model's* to announce, not this pipeline's.
    assert runner.written == ["layout.json"]


def test_it_declares_everything_the_execution_leaves_behind() -> None:
    description = a_pipeline().description()

    assert description.signature.input == ["image.jpg"]
    assert description.signature.output == ["layout.json", "transcription.musicxml"]


def test_a_model_that_fails_fails_the_pipeline() -> None:
    def refuses(call: ModelCall, files: dict[str, bytes]) -> None:
        raise RuntimeError("Nothing to say about this page.")

    runner = PipelineRunner({"image.jpg": a_jpeg()})
    runner.register_model(HELLO_MODEL, refuses)

    with pytest.raises(ModelExecutionFailed):
        runner.run(a_pipeline(), input=["image.jpg"])

    assert "layout.json" not in runner.files


def test_a_transcription_that_is_not_the_pinned_models_is_refused() -> None:
    def writes_something_else(call: ModelCall, files: dict[str, bytes]) -> None:
        files["transcription.musicxml"] = b"<score-partwise/>"

    runner = PipelineRunner({"image.jpg": a_jpeg()})
    runner.register_model(HELLO_MODEL, writes_something_else)

    with pytest.raises(ValueError, match="does not say how many bytes"):
        runner.run(a_pipeline(), input=["image.jpg"])


# --- the pieces, on their own ------------------------------------------------


def test_the_byte_count_is_read_out_of_the_lyric() -> None:
    assert byte_count(musicxml(12345)) == 12345


def test_a_margin_wider_than_the_image_does_not_make_a_negative_box() -> None:
    [annotation] = layout_document(30, 30, margin=20)["annotations"]

    assert annotation["bbox"] == [20, 20, 0, 0]
    assert annotation["area"] == 0


def test_the_same_page_produces_the_same_bytes_twice() -> None:
    # Nothing in the document is dated or randomised, so a change to a page's
    # layout is visible as a diff rather than lost in noise.
    assert layout_document(100, 60, 20) == layout_document(100, 60, 20)
