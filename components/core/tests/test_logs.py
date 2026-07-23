import json

import pytest
from pydantic import ValidationError

from musibot.core.execution import PipelineExecutionRef
from musibot.core.logs import (
    LOGS_EXCHANGE,
    LogMessage,
    LogSource,
    ProgressMessage,
    parse_log_message,
    serialize_message,
)

LOG = {
    "type": "log",
    "pipeline_execution": {"page_id": "7Kf2mP9xLwQa", "execution_id": 1},
    "source": {"kind": "worker", "name": "staff-detector", "instance_id": "8Lw4tR6yBn1c"},
    "level": "info",
    "message": "transcribing staff 3/12",
    "timestamp": "2026-07-23T15:04:05Z",
}

PROGRESS = {
    "type": "progress",
    "pipeline_execution": {"page_id": "7Kf2mP9xLwQa", "execution_id": 1},
    "source": {"kind": "worker", "name": "staff-detector", "instance_id": "8Lw4tR6yBn1c"},
    "message": "staff 3/12",
    "fraction": 0.25,
}


def test_the_documented_log_parses() -> None:
    message = parse_log_message(json.dumps(LOG))

    assert isinstance(message, LogMessage)
    assert message.message == "transcribing staff 3/12"
    assert message.pipeline_execution.execution_id == 1
    assert message.source.name == "staff-detector"


def test_the_documented_progress_parses() -> None:
    message = parse_log_message(json.dumps(PROGRESS))

    assert isinstance(message, ProgressMessage)
    assert message.fraction == 0.25


@pytest.mark.parametrize("payload", [LOG, PROGRESS])
def test_log_messages_round_trip(payload: dict[str, object]) -> None:
    message = parse_log_message(json.dumps(payload))

    assert parse_log_message(serialize_message(message)) == message


def test_a_log_of_an_unknown_level_is_refused() -> None:
    payload = json.loads(json.dumps(LOG))
    payload["level"] = "catastrophe"

    with pytest.raises(ValidationError):
        parse_log_message(json.dumps(payload))


def test_a_log_of_an_unknown_source_kind_is_refused() -> None:
    payload = json.loads(json.dumps(LOG))
    payload["source"]["kind"] = "goblin"

    with pytest.raises(ValidationError):
        parse_log_message(json.dumps(payload))


def test_a_log_without_a_timestamp_is_allowed() -> None:
    # A source without a clock still gets its output shown, rather than dropped.
    payload = json.loads(json.dumps(LOG))
    del payload["timestamp"]

    message = parse_log_message(json.dumps(payload))

    assert isinstance(message, LogMessage)
    assert message.timestamp is None


def test_progress_may_report_a_message_or_a_fraction_or_neither() -> None:
    bare = ProgressMessage(
        pipeline_execution=PipelineExecutionRef(page_id="7Kf2mP9xLwQa", execution_id=1),
        source=LogSource(kind="orchestrator", name="ref", instance_id="3xQ7nP2vKm9w"),
    )

    assert bare.message is None
    assert bare.fraction is None


def test_a_log_can_be_built_in_code() -> None:
    log = LogMessage(
        pipeline_execution=PipelineExecutionRef(page_id="7Kf2mP9xLwQa", execution_id=1),
        source=LogSource(kind="worker", name="staff-detector", instance_id="8Lw4tR6yBn1c"),
        message="hello",
    )

    assert log.level == "info"  # the default
    assert json.loads(serialize_message(log))["type"] == "log"


def test_the_exchange_name_matches_the_documentation() -> None:
    assert LOGS_EXCHANGE == "musibot.logs"
