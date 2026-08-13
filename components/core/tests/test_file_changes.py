import json

import pytest
from pydantic import ValidationError

from musibot.core.execution import PipelineExecutionRef
from musibot.core.file_changes import (
    FILE_CHANGES_EXCHANGE,
    FilesChanged,
    parse_file_change_message,
    serialize_message,
)

CHANGE = {
    "type": "files-changed",
    "pipeline_execution": {"page_id": "7Kf2mP9xLwQa", "execution_id": 1},
    "paths": ["Staves/1/transcription.musicxml", "Staves/1/transcription.lmx"],
}


def test_the_documented_notice_parses() -> None:
    message = parse_file_change_message(json.dumps(CHANGE))

    assert message.paths == ["Staves/1/transcription.musicxml", "Staves/1/transcription.lmx"]
    assert message.pipeline_execution.page_id == "7Kf2mP9xLwQa"


def test_a_notice_round_trips() -> None:
    message = parse_file_change_message(json.dumps(CHANGE))

    assert parse_file_change_message(serialize_message(message)) == message


def test_a_path_that_escapes_its_page_is_refused() -> None:
    # The same validation every other path in Musibot goes through: a notice is
    # a message off a queue, so it is parsed rather than trusted.
    payload = json.loads(json.dumps(CHANGE))
    payload["paths"] = ["../somebody-elses-page/image.jpg"]

    with pytest.raises(ValidationError):
        parse_file_change_message(json.dumps(payload))


def test_a_log_message_is_not_a_file_change() -> None:
    payload = {
        "type": "log",
        "pipeline_execution": {"page_id": "7Kf2mP9xLwQa", "execution_id": 1},
        "source": {"kind": "worker", "name": "staff-detector", "instance_id": "8Lw4tR6yBn1c"},
        "message": "7 staves",
    }

    with pytest.raises(ValidationError):
        parse_file_change_message(json.dumps(payload))


def test_a_notice_can_be_built_in_code() -> None:
    notice = FilesChanged(
        pipeline_execution=PipelineExecutionRef(page_id="7Kf2mP9xLwQa", execution_id=1),
        paths=["layout.json"],
    )

    assert json.loads(serialize_message(notice))["type"] == "files-changed"


def test_the_exchange_name_matches_the_documentation() -> None:
    assert FILE_CHANGES_EXCHANGE == "musibot.file-changes"
