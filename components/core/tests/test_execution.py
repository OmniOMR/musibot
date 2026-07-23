import json

import pytest
from pydantic import ValidationError

from musibot.core.execution import (
    MODEL_EXECUTIONS_EXCHANGE,
    PIPELINE_EXECUTIONS_EXCHANGE,
    ModelExecutionResult,
    ModelExecutionStart,
    ModelExecutionTerminate,
    NameAndVersion,
    OrchestratorRef,
    PipelineExecutionRef,
    PipelineExecutionResult,
    PipelineExecutionStart,
    PipelineExecutionTerminate,
    WorkerRef,
    generate_model_execution_id,
    parse_model_execution_message,
    parse_pipeline_execution_message,
    routing_key,
    serialize_message,
)

# The messages exactly as `docs/rabbitmq-exchanges-and-messages.md` documents.

PIPELINE_START = {
    "type": "pipeline-execution-start",
    "page_id": "7Kf2mP9xLwQa",
    "execution_id": 1,
    "pipeline": {"name": "hello-world", "version": "1.0.0"},
    "parameters": {},
    "timeout_seconds": 300,
}

PIPELINE_RESULT = {
    "type": "pipeline-execution-result",
    "page_id": "7Kf2mP9xLwQa",
    "execution_id": 1,
    "state": "completed",
    "error": None,
    "orchestrator": {"name": "reference-orchestrator", "instance_id": "3xQ7nP2vKm9w"},
}

MODEL_START = {
    "type": "model-execution-start",
    "model_execution_id": "8Lw4tR6yBn1c",
    "model": {"name": "staff-detector", "version": "2026-07-22"},
    "page_id": "7Kf2mP9xLwQa",
    "input": ["image.jpg"],
    "parameters": {},
    "pipeline_execution": {"page_id": "7Kf2mP9xLwQa", "execution_id": 1},
    "timeout_seconds": 300,
}

MODEL_RESULT = {
    "type": "model-execution-result",
    "model_execution_id": "8Lw4tR6yBn1c",
    "state": "failed",
    "error": "No staves found in the image.",
    "worker": {"name": "staff-detector", "instance_id": "8Lw4tR6yBn1c"},
}


def test_routing_key_joins_name_and_version_with_an_at_sign() -> None:
    # `@`, not `.`, because `direct` routing on a dotted version would be a mess.
    assert routing_key("hello-world", "1.0.0") == "hello-world@1.0.0"


def test_the_documented_pipeline_start_parses() -> None:
    message = parse_pipeline_execution_message(json.dumps(PIPELINE_START))

    assert isinstance(message, PipelineExecutionStart)
    assert message.pipeline.name == "hello-world"
    assert message.timeout_seconds == 300


def test_the_documented_pipeline_result_parses() -> None:
    message = parse_pipeline_execution_message(json.dumps(PIPELINE_RESULT))

    assert isinstance(message, PipelineExecutionResult)
    assert message.state == "completed"
    assert message.orchestrator.instance_id == "3xQ7nP2vKm9w"


def test_the_documented_model_start_parses() -> None:
    message = parse_model_execution_message(json.dumps(MODEL_START))

    assert isinstance(message, ModelExecutionStart)
    assert message.model.version == "2026-07-22"
    assert message.pipeline_execution.execution_id == 1


def test_the_documented_model_result_parses() -> None:
    message = parse_model_execution_message(json.dumps(MODEL_RESULT))

    assert isinstance(message, ModelExecutionResult)
    assert message.state == "failed"
    assert message.error == "No staves found in the image."


@pytest.mark.parametrize("payload", [PIPELINE_START, PIPELINE_RESULT])
def test_pipeline_messages_round_trip(payload: dict[str, object]) -> None:
    message = parse_pipeline_execution_message(json.dumps(payload))

    assert parse_pipeline_execution_message(serialize_message(message)) == message


@pytest.mark.parametrize("payload", [MODEL_START, MODEL_RESULT])
def test_model_messages_round_trip(payload: dict[str, object]) -> None:
    message = parse_model_execution_message(json.dumps(payload))

    assert parse_model_execution_message(serialize_message(message)) == message


def test_the_two_exchanges_do_not_share_a_message_space() -> None:
    # A pipeline-result consumer must reject a model-start message rather than
    # silently accept it, so each exchange parses only its own set.
    with pytest.raises(ValidationError):
        parse_pipeline_execution_message(json.dumps(MODEL_START))

    with pytest.raises(ValidationError):
        parse_model_execution_message(json.dumps(PIPELINE_START))


def test_a_terminate_carries_only_what_identifies_the_execution() -> None:
    pipeline_terminate = parse_pipeline_execution_message(
        serialize_message(PipelineExecutionTerminate(page_id="7Kf2mP9xLwQa", execution_id=2))
    )
    assert isinstance(pipeline_terminate, PipelineExecutionTerminate)

    model_terminate = parse_model_execution_message(
        serialize_message(ModelExecutionTerminate(model_execution_id="8Lw4tR6yBn1c"))
    )
    assert isinstance(model_terminate, ModelExecutionTerminate)


def test_a_start_without_its_timeout_is_refused() -> None:
    payload = json.loads(json.dumps(PIPELINE_START))
    del payload["timeout_seconds"]

    with pytest.raises(ValidationError):
        parse_pipeline_execution_message(json.dumps(payload))


def test_a_result_of_an_unknown_state_is_refused() -> None:
    payload = json.loads(json.dumps(PIPELINE_RESULT))
    payload["state"] = "somewhere-in-between"

    with pytest.raises(ValidationError):
        parse_pipeline_execution_message(json.dumps(payload))


def test_a_model_start_naming_an_escaping_input_is_refused() -> None:
    payload = json.loads(json.dumps(MODEL_START))
    payload["input"] = ["../../etc/passwd"]

    with pytest.raises(ValidationError):
        parse_model_execution_message(json.dumps(payload))


def test_a_model_start_with_a_malformed_page_id_is_refused() -> None:
    payload = json.loads(json.dumps(MODEL_START))
    payload["page_id"] = "not-a-page"

    with pytest.raises(ValidationError):
        parse_model_execution_message(json.dumps(payload))


def test_unknown_fields_are_ignored_so_the_protocol_can_grow() -> None:
    payload = json.loads(json.dumps(PIPELINE_START))
    payload["invented_later"] = True

    assert isinstance(parse_pipeline_execution_message(json.dumps(payload)), PipelineExecutionStart)


def test_messages_can_be_built_in_code() -> None:
    start = ModelExecutionStart(
        model_execution_id=generate_model_execution_id(),
        model=NameAndVersion(name="staff-detector", version="2026-07-22"),
        page_id="7Kf2mP9xLwQa",
        input=["image.jpg"],
        pipeline_execution=PipelineExecutionRef(page_id="7Kf2mP9xLwQa", execution_id=1),
        timeout_seconds=300,
    )

    assert json.loads(serialize_message(start))["type"] == "model-execution-start"


def test_a_pipeline_result_carries_who_produced_it() -> None:
    result = PipelineExecutionResult(
        page_id="7Kf2mP9xLwQa",
        execution_id=1,
        state="failed",
        error="boom",
        orchestrator=OrchestratorRef(name="ref", instance_id="3xQ7nP2vKm9w"),
    )

    assert result.orchestrator.name == "ref"


def test_a_model_result_carries_who_produced_it() -> None:
    result = ModelExecutionResult(
        model_execution_id="8Lw4tR6yBn1c",
        state="completed",
        worker=WorkerRef(name="staff-detector", instance_id="8Lw4tR6yBn1c"),
    )

    assert result.worker.name == "staff-detector"


def test_model_execution_ids_are_distinct() -> None:
    assert len({generate_model_execution_id() for _ in range(100)}) == 100


def test_the_exchange_names_match_the_documentation() -> None:
    assert PIPELINE_EXECUTIONS_EXCHANGE == "musibot.pipeline-executions"
    assert MODEL_EXECUTIONS_EXCHANGE == "musibot.model-executions"
