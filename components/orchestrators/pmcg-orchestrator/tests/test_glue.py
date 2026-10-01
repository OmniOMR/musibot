"""`GluePipelineV1` and `V2`: a layout and its staff transcriptions in, one page out."""

from xml.etree import ElementTree

import pytest
from musibot.orchestrator_head.testing import PipelineRunner

from pmcg_orchestrator.glue import GluePipeline, GluePipelineV1, GluePipelineV2
from pmcg_orchestrator.page_from_staff import (
    PageFromStaffPipeline,
    PageFromStaffPipelineV1,
    PageFromStaffPipelineV2,
)
from tests.fakes import (
    LAYOUT_MODEL,
    STAFF_MODEL,
    a_layout,
    a_page,
    a_runner,
    a_staff_transcription,
    fails_staff,
)

# Three single-staff systems down the 400x300 page the fakes make, each with a
# system box around it: one instrument's three lines of music.
THREE_STAVES = ((20, 20, 360, 40), (20, 110, 360, 40), (20, 200, 360, 40))
THREE_SYSTEMS = ((10, 10, 380, 60), (10, 100, 380, 60), (10, 190, 380, 60))

# Each version of the gluing, beside the version of `mzk-page` that glues alike.
VERSIONS = [
    pytest.param(GluePipelineV1, PageFromStaffPipelineV1, id="v1"),
    pytest.param(GluePipelineV2, PageFromStaffPipelineV2, id="v2"),
]


@pytest.fixture(params=[GluePipelineV1, GluePipelineV2], ids=["v1", "v2"])
def implementation(request: pytest.FixtureRequest) -> type[GluePipeline]:
    cls: type[GluePipeline] = request.param
    return cls


def a_glue_runner(
    images: list[int | str],
    transcriptions: list[int | str],
    staves: tuple[tuple[int, int, int, int], ...] = THREE_STAVES,
    systems: tuple[tuple[int, int, int, int], ...] = THREE_SYSTEMS,
) -> tuple[PipelineRunner, list[str]]:
    """A page already sliced and transcribed, and the input list naming all of it."""
    files = {"layout.json": a_layout(*staves, systems=systems)}
    for staff in images:
        files[f"Staves/{staff}/image.jpg"] = a_page(100, 40)
    for staff in transcriptions:
        files[f"Staves/{staff}/transcription.musicxml"] = a_staff_transcription(
            f"staff {staff}"
        ).encode("utf-8")
    return PipelineRunner(files), sorted(files)


def glued(runner: PipelineRunner) -> ElementTree.Element:
    return ElementTree.fromstring(runner.files["transcription.musicxml"])


def lyrics(runner: PipelineRunner) -> list[str | None]:
    return [text.text for text in glued(runner).iter("text")]


def words(runner: PipelineRunner) -> list[str | None]:
    return [words.text for words in glued(runner).iter("words")]


# --- the same page mzk-page writes -------------------------------------------


@pytest.mark.parametrize("glue, page", VERSIONS)
def test_it_glues_exactly_what_mzk_page_would_have(
    glue: type[GluePipeline], page: type[PageFromStaffPipeline]
) -> None:
    """Which is what lets a User run the steps of `mzk-page` by hand, correcting
    what lies between them, and get the page `mzk-page` would have written.
    One staff failing is part of it: a failure has to come out the same too."""
    whole = a_runner(*THREE_STAVES, systems=THREE_SYSTEMS, staff_model=fails_staff(2))
    whole.run(
        page("mzk-page", "x", layout_model=LAYOUT_MODEL, staff_model=STAFF_MODEL),
        input=["image.jpg"],
    )

    by_hand = PipelineRunner(dict(whole.files))
    del by_hand.files["transcription.musicxml"]
    by_hand.run(
        glue("pmcg-glue", "x"),
        input=sorted(path for path in by_hand.files if path.startswith(("Staves/", "layout"))),
    )

    assert by_hand.files["transcription.musicxml"] == whole.files["transcription.musicxml"]


# --- pairing -----------------------------------------------------------------


def test_it_runs_no_model_and_writes_only_the_page(implementation: type[GluePipeline]) -> None:
    runner, files = a_glue_runner(images=[1, 2, 3], transcriptions=[1, 2, 3])

    runner.run(implementation("pmcg-glue", "x"), input=files)

    assert runner.model_calls == []
    assert runner.written == ["transcription.musicxml"]
    assert lyrics(runner) == ["staff 1", "staff 2", "staff 3"]


def test_a_staff_with_an_image_and_no_transcription_failed(
    implementation: type[GluePipeline],
) -> None:
    runner, files = a_glue_runner(images=[1, 2, 3], transcriptions=[1, 3])

    runner.run(implementation("pmcg-glue", "x"), input=files)

    # It keeps its place, says so in the score, and is named in the log.
    assert lyrics(runner) == ["staff 1", "staff 3"]
    assert len(words(runner)) == 1
    errors = [line.message for line in runner.logs if line.level == "error"]
    assert errors == ["Staff 2 has no transcription."]


def test_a_page_with_no_transcriptions_at_all_is_a_failure(
    implementation: type[GluePipeline],
) -> None:
    runner, files = a_glue_runner(images=[1, 2, 3], transcriptions=[])

    with pytest.raises(ValueError, match="None of the 3 staves has a transcription"):
        runner.run(implementation("pmcg-glue", "x"), input=files)


def test_a_transcription_without_an_image_is_left_out_and_said(
    implementation: type[GluePipeline],
) -> None:
    """The images name the staves, so a transcription with none is not one."""
    runner, files = a_glue_runner(images=[1, 2, 3], transcriptions=[1, 2, 3, 9])

    runner.run(implementation("pmcg-glue", "x"), input=files)

    assert lyrics(runner) == ["staff 1", "staff 2", "staff 3"]
    warnings = [line.message for line in runner.logs if line.level == "warning"]
    assert warnings == ["Ignoring the transcriptions of staves 9, which have no staff image."]


def test_staves_beyond_the_layout_are_left_out_and_said(
    implementation: type[GluePipeline],
) -> None:
    """Paired from the top, as `zip` pairs, and the rest named in the log."""
    runner, files = a_glue_runner(images=[1, 2, 3, 4], transcriptions=[1, 2, 3, 4])

    runner.run(implementation("pmcg-glue", "x"), input=files)

    assert lyrics(runner) == ["staff 1", "staff 2", "staff 3"]
    warnings = [line.message for line in runner.logs if line.level == "warning"]
    assert warnings == [
        "The layout has 3 staves and 4 staff images were given; leaving out staves 4."
    ]


def test_layout_staves_beyond_the_images_are_left_out_and_said(
    implementation: type[GluePipeline],
) -> None:
    runner, files = a_glue_runner(images=[1, 2], transcriptions=[1, 2])

    runner.run(implementation("pmcg-glue", "x"), input=files)

    # Nothing stands in for the third staff: there is no image to say it exists.
    assert lyrics(runner) == ["staff 1", "staff 2"]
    assert words(runner) == []
    warnings = [line.message for line in runner.logs if line.level == "warning"]
    assert warnings == [
        (
            "The layout has 3 staves and 2 staff images were given; "
            "leaving out the bottom 1 of the layout's staves."
        )
    ]


def test_staff_folders_may_have_gaps(implementation: type[GluePipeline]) -> None:
    """The Musicorpus Specification numbers empty staves too, which the layout
    does not box as staves, so `1, 2, 4` is three staves in order."""
    runner, files = a_glue_runner(images=[1, 2, 4], transcriptions=[1, 2, 4])

    runner.run(implementation("pmcg-glue", "x"), input=files)

    assert lyrics(runner) == ["staff 1", "staff 2", "staff 4"]
    assert runner.logs and all(line.level == "info" for line in runner.logs)


def test_staff_folders_are_paired_by_number_not_by_spelling(
    implementation: type[GluePipeline],
) -> None:
    # Sorted as text, 10 would come before 9.
    runner, files = a_glue_runner(images=[9, 10, 11], transcriptions=[9, 10, 11])

    runner.run(implementation("pmcg-glue", "x"), input=files)

    assert lyrics(runner) == ["staff 9", "staff 10", "staff 11"]


def test_a_staff_folder_that_is_not_a_number_is_refused(
    implementation: type[GluePipeline],
) -> None:
    runner, files = a_glue_runner(images=[1, "two", 3], transcriptions=[1, "two", 3])

    with pytest.raises(ValueError, match="'two' .* is not one"):
        runner.run(implementation("pmcg-glue", "x"), input=files)


def test_two_folders_with_one_number_are_refused(implementation: type[GluePipeline]) -> None:
    runner, files = a_glue_runner(images=[1, "01", 3], transcriptions=[1, "01", 3])

    with pytest.raises(ValueError, match="are the same number"):
        runner.run(implementation("pmcg-glue", "x"), input=files)


def test_a_layout_with_no_staves_has_nothing_to_glue(implementation: type[GluePipeline]) -> None:
    runner, files = a_glue_runner(images=[1], transcriptions=[1], staves=(), systems=())

    with pytest.raises(ValueError, match="no staves to glue"):
        runner.run(implementation("pmcg-glue", "x"), input=files)


# --- each version ------------------------------------------------------------


def test_version_1_glues_every_staff_into_one_part() -> None:
    runner, files = a_glue_runner(images=[1, 2, 4], transcriptions=[1, 4])

    runner.run(GluePipelineV1("pmcg-glue", "1"), input=files)

    assert [part.get("id") for part in glued(runner).findall("part")] == ["P1"]
    # A placeholder names the staff by its own folder, which is what the User
    # has in front of them.
    assert words(runner) == ["Staff 2 could not be transcribed"]


def test_version_2_works_out_instruments_from_the_staves_there_are() -> None:
    """Three systems in the layout, two staff images: the bottom system is
    dropped from the layout rather than written as an instrument's silence."""
    runner, files = a_glue_runner(images=[1, 2], transcriptions=[1, 2])

    runner.run(GluePipelineV2("pmcg-glue", "2"), input=files)

    [part] = glued(runner).findall("part")
    assert len(part.findall("measure")) == 2


def test_version_2_names_a_placeholder_by_the_layout_s_staff() -> None:
    runner, files = a_glue_runner(images=[1, 2, 4], transcriptions=[1, 2])

    runner.run(GluePipelineV2("pmcg-glue", "2"), input=files)

    # Staff folder 4 is the layout's third staff.
    assert words(runner) == ["Cannot transcribe staff 3"]


# --- the declaration ---------------------------------------------------------


def test_it_declares_the_layout_crops_and_transcriptions_in_and_the_page_out(
    implementation: type[GluePipeline],
) -> None:
    signature = implementation("pmcg-glue", "x").description().signature

    assert signature.input == [
        "layout.json",
        "Staves/{*}/image.jpg",
        "Staves/{*}/transcription.musicxml",
    ]
    assert signature.output == ["transcription.musicxml"]
