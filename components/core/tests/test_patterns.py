import pytest
from pydantic import BaseModel, ValidationError

from musibot.core.patterns import (
    FilePattern,
    InvalidFilePattern,
    PageFilePattern,
    SignatureMismatch,
    Slot,
    check_input_files,
    check_slot_names,
    concrete_outputs,
    parse_file_pattern,
    parse_file_patterns,
)

# --- parsing -----------------------------------------------------------------


def test_a_path_with_no_slots_is_a_pattern_that_names_one_file() -> None:
    pattern = parse_file_pattern("image.jpg")

    assert pattern.is_concrete
    assert not pattern.accepts_many
    assert not pattern.optional
    assert pattern.concrete_path == "image.jpg"


@pytest.mark.parametrize(
    ("text", "slot"),
    [
        ("Staves/{}/image.jpg", Slot(name=None, many=False)),
        ("Staves/{s}/image.jpg", Slot(name="s", many=False)),
        ("Staves/{*}/image.jpg", Slot(name=None, many=True)),
        ("Staves/{*s}/image.jpg", Slot(name="s", many=True)),
    ],
)
def test_every_spelling_of_a_slot_parses(text: str, slot: Slot) -> None:
    pattern = parse_file_pattern(text)

    assert pattern.segments == ("Staves", slot, "image.jpg")
    assert not pattern.is_concrete
    assert pattern.accepts_many is slot.many


def test_a_trailing_question_mark_marks_the_entry_optional() -> None:
    pattern = parse_file_pattern("layout.json?")

    assert pattern.optional
    assert pattern.text == "layout.json?"
    assert pattern.concrete_path == "layout.json"


def test_a_question_mark_inside_a_name_is_part_of_the_name() -> None:
    assert not parse_file_pattern("why?.jpg").optional


@pytest.mark.parametrize(
    "text",
    [
        "image.{v}.jpg",  # a slot is a whole segment, not part of one
        "{",
        "}",
        "Staves/{s/image.jpg",
        "Staves/{s}}/image.jpg",
        "Staves/{ }/image.jpg",
        "Staves/{s t}/image.jpg",
        "Staves/{**}/image.jpg",
        "Staves/{*s*}/image.jpg",
    ],
)
def test_a_malformed_slot_is_refused(text: str) -> None:
    with pytest.raises(InvalidFilePattern):
        parse_file_pattern(text)


@pytest.mark.parametrize(
    "text",
    ["", "?", "/image.jpg", "Staves//image.jpg", "../image.jpg", "Staves/{s}/../image.jpg"],
)
def test_a_pattern_obeys_every_rule_a_path_obeys(text: str) -> None:
    with pytest.raises(InvalidFilePattern):
        parse_file_pattern(text)


def test_a_pattern_is_validated_where_it_appears_in_a_message() -> None:
    class Message(BaseModel):
        entry: PageFilePattern

    assert Message(entry="Staves/{s}/image.jpg").entry == "Staves/{s}/image.jpg"

    with pytest.raises(ValidationError):
        Message(entry="image.{v}.jpg")


# --- slot names --------------------------------------------------------------


def test_one_name_may_not_mean_both_one_instance_and_every_instance() -> None:
    with pytest.raises(InvalidFilePattern):
        check_slot_names(parse_file_patterns(["Staves/{s}/image.jpg", "Staves/{*s}/layout.json"]))


def test_a_name_repeated_with_the_same_arity_is_the_point_of_names() -> None:
    check_slot_names(
        parse_file_patterns(["Staves/{s}/image.jpg", "Staves/{s}/transcription.musicxml"])
    )


# --- matching an input list --------------------------------------------------


def check(patterns: list[str], file_paths: list[str]) -> None:
    check_input_files(parse_file_patterns(patterns), file_paths)


def test_a_page_level_input_list_fits_a_page_level_signature() -> None:
    check(["image.jpg"], ["image.jpg"])


def test_a_file_the_signature_does_not_name_is_refused() -> None:
    with pytest.raises(SignatureMismatch, match="not named by the signature"):
        check(["image.jpg"], ["image.jpg", "metadata.json"])


def test_a_missing_required_file_is_refused() -> None:
    with pytest.raises(SignatureMismatch, match="names no 'layout.json'"):
        check(["image.jpg", "layout.json"], ["image.jpg"])


def test_a_missing_optional_file_is_fine() -> None:
    check(["image.jpg", "layout.json?"], ["image.jpg"])


def test_a_file_named_twice_is_refused() -> None:
    with pytest.raises(SignatureMismatch, match="named twice"):
        check(["Staves/{*}/image.jpg"], ["Staves/1/image.jpg", "Staves/1/image.jpg"])


def test_one_instance_means_one_file() -> None:
    check(["Staves/{s}/image.jpg"], ["Staves/7/image.jpg"])


def test_twelve_staves_handed_to_a_one_staff_model_are_refused() -> None:
    with pytest.raises(SignatureMismatch, match="names one file"):
        check(
            ["Staves/{s}/image.jpg"],
            [f"Staves/{number}/image.jpg" for number in range(1, 13)],
        )


def test_a_wildcard_takes_as_many_as_arrive() -> None:
    check(
        ["Staves/{*}/image.jpg"],
        ["Staves/1/image.jpg", "Staves/4/image.jpg", "Staves/17/image.jpg"],
    )


def test_a_wildcard_is_content_with_none() -> None:
    check(["Staves/{*}/image.jpg"], [])


def test_a_bound_name_must_be_the_same_instance_everywhere() -> None:
    check(
        ["Staves/{s}/image.jpg", "Staves/{s}/layout.json"],
        ["Staves/7/image.jpg", "Staves/7/layout.json"],
    )

    with pytest.raises(SignatureMismatch, match="same instances throughout"):
        check(
            ["Staves/{s}/image.jpg", "Staves/{s}/layout.json"],
            ["Staves/7/image.jpg", "Staves/8/layout.json"],
        )


def test_a_bound_wildcard_must_be_the_same_set_on_both_entries() -> None:
    check(
        ["Staves/{*s}/image.jpg", "Staves/{*s}/layout.json"],
        [
            "Staves/1/image.jpg",
            "Staves/2/image.jpg",
            "Staves/1/layout.json",
            "Staves/2/layout.json",
        ],
    )

    with pytest.raises(SignatureMismatch, match="same instances throughout"):
        check(
            ["Staves/{*s}/image.jpg", "Staves/{*s}/layout.json"],
            ["Staves/1/image.jpg", "Staves/2/image.jpg", "Staves/1/layout.json"],
        )


def test_an_anonymous_slot_binds_nothing_so_two_of_them_are_unrelated() -> None:
    check(
        ["Staves/{*}/image.jpg", "Grandstaves/{*}/image.jpg"],
        ["Staves/1/image.jpg", "Grandstaves/6-7/image.jpg"],
    )


def test_an_optional_entry_nobody_sent_does_not_contradict_the_ones_that_arrived() -> None:
    check(
        ["Staves/{s}/image.jpg", "Staves/{s}/layout.json?"],
        ["Staves/7/image.jpg"],
    )


def test_a_page_level_file_may_travel_beside_a_staff_level_one() -> None:
    check(
        ["image.jpg", "Staves/{s}/image.jpg"],
        ["image.jpg", "Staves/7/image.jpg"],
    )


def test_a_lone_instance_slot_beside_a_wildcard_is_still_one_instance() -> None:
    patterns = ["Systems/{sys}/Staves/{*}/image.jpg"]

    check(patterns, ["Systems/2-7/Staves/2/image.jpg", "Systems/2-7/Staves/3/image.jpg"])

    with pytest.raises(SignatureMismatch, match="names one instance"):
        check(patterns, ["Systems/2-7/Staves/2/image.jpg", "Systems/9-14/Staves/9/image.jpg"])


def test_a_signature_naming_no_input_accepts_nothing() -> None:
    check([], [])

    with pytest.raises(SignatureMismatch, match="names no input"):
        check([], ["image.jpg"])


# --- promised outputs --------------------------------------------------------


def test_only_the_slot_free_required_outputs_are_promised_outright() -> None:
    patterns = parse_file_patterns(
        [
            "layout.json",
            "warnings.json?",
            "Staves/{*}/image.jpg",
            "Staves/{s}/transcription.musicxml",
        ]
    )

    assert concrete_outputs(patterns) == ["layout.json"]


# --- the models we expect to deploy ------------------------------------------


DEPLOYABLE_MODELS: list[tuple[list[str], list[str], list[str]]] = [
    (["image.jpg"], ["layout.json"], ["image.jpg"]),
    (["image.jpg"], ["transcription.musicxml"], ["image.jpg"]),
    (
        ["Staves/{s}/image.jpg"],
        ["Staves/{s}/transcription.musicxml"],
        ["Staves/7/image.jpg"],
    ),
    (
        ["image.jpg", "layout.json"],
        ["Staves/{*}/image.jpg"],
        ["image.jpg", "layout.json"],
    ),
    (
        ["Staves/{*}/transcription.musicxml"],
        ["Systems/{*}/transcription.musicxml"],
        ["Staves/2/transcription.musicxml", "Staves/4/transcription.musicxml"],
    ),
    (
        ["Grandstaves/{*}/image.jpg"],
        ["Staves/{*}/image.jpg"],
        ["Grandstaves/6-7/image.jpg", "Grandstaves/13-14/image.jpg"],
    ),
]


@pytest.mark.parametrize(("input_patterns", "output_patterns", "file_paths"), DEPLOYABLE_MODELS)
def test_the_models_in_the_signatures_document_are_expressible(
    input_patterns: list[str], output_patterns: list[str], file_paths: list[str]
) -> None:
    """Every row of the model table in `docs/signatures.md`, with an input list
    a *User* would plausibly send it."""
    patterns = parse_file_patterns([*input_patterns, *output_patterns])
    check_slot_names(patterns)

    check(input_patterns, file_paths)


def test_a_pattern_matches_only_paths_of_its_own_depth() -> None:
    pattern = parse_file_pattern("Staves/{*}/image.jpg")

    assert pattern.match("Staves/1/image.jpg")
    assert not pattern.match("image.jpg")
    assert not pattern.match("Staves/1/2/image.jpg")
    assert not pattern.match("Systems/1/image.jpg")
    assert not pattern.match("Staves/1/layout.json")


def test_a_pattern_is_a_dataclass_that_carries_what_was_written() -> None:
    assert parse_file_pattern("layout.json?") == FilePattern(
        text="layout.json?", segments=("layout.json",), optional=True
    )
