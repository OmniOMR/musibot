import json

import pytest
from pydantic import ValidationError

from musibot.core.discovery import (
    DISCOVERY_EXCHANGE,
    DISCOVERY_PROBE_EXCHANGE,
    ENTRY_TTL_SECONDS,
    HEARTBEAT_INTERVAL_SECONDS,
    Goodbye,
    ModelDescription,
    OrchestratorAnnouncement,
    OrchestratorProvider,
    Probe,
    Signature,
    WorkerAnnouncement,
    WorkerProvider,
    generate_instance_id,
    parse_discovery_message,
    serialize_message,
)

# The messages exactly as `docs/discovery.md` documents them.

ORCHESTRATOR_ANNOUNCEMENT = {
    "type": "announcement",
    "provider": {
        "kind": "orchestrator",
        "name": "reference-orchestrator",
        "instance_id": "3xQ7nP2vKm9w",
        "head_version": "0.1.0",
    },
    "pipelines": [
        {
            "name": "hello-world",
            "version": "1.0.0",
            "signature": {"input": ["image.jpg"], "output": ["transcription.musicxml"]},
        }
    ],
}

WORKER_ANNOUNCEMENT = {
    "type": "announcement",
    "provider": {
        "kind": "worker",
        "name": "staff-detector",
        "instance_id": "8Lw4tR6yBn1c",
        "head_version": "0.1.0",
    },
    "model": {
        "name": "staff-detector",
        "version": "2026-07-22",
        "signature": {"input": ["image.jpg"], "output": ["layout.json"]},
        "supports_batching": True,
    },
}

GOODBYE = {
    "type": "goodbye",
    "provider": {"kind": "worker", "name": "staff-detector", "instance_id": "8Lw4tR6yBn1c"},
}

PROBE = {"type": "probe"}


def test_the_documented_orchestrator_announcement_parses() -> None:
    message = parse_discovery_message(json.dumps(ORCHESTRATOR_ANNOUNCEMENT))

    assert isinstance(message, OrchestratorAnnouncement)
    assert message.provider.name == "reference-orchestrator"
    assert message.pipelines[0].name == "hello-world"
    assert message.pipelines[0].signature.output == ["transcription.musicxml"]


def test_the_documented_worker_announcement_parses() -> None:
    message = parse_discovery_message(json.dumps(WORKER_ANNOUNCEMENT))

    assert isinstance(message, WorkerAnnouncement)
    assert message.model.name == "staff-detector"
    assert message.model.supports_batching is True


def test_the_documented_goodbye_parses() -> None:
    message = parse_discovery_message(json.dumps(GOODBYE))

    assert isinstance(message, Goodbye)
    assert message.provider.instance_id == "8Lw4tR6yBn1c"


def test_the_documented_probe_parses() -> None:
    assert isinstance(parse_discovery_message(json.dumps(PROBE)), Probe)


@pytest.mark.parametrize(
    "payload", [ORCHESTRATOR_ANNOUNCEMENT, WORKER_ANNOUNCEMENT, GOODBYE, PROBE]
)
def test_every_message_survives_a_round_trip(payload: dict[str, object]) -> None:
    message = parse_discovery_message(json.dumps(payload))

    assert parse_discovery_message(serialize_message(message)) == message


def test_the_two_announcements_are_told_apart_by_their_provider() -> None:
    # Both carry "type": "announcement", so the discriminator has to look
    # deeper than the type field.
    assert isinstance(parse_discovery_message(json.dumps(WORKER_ANNOUNCEMENT)), WorkerAnnouncement)
    assert isinstance(
        parse_discovery_message(json.dumps(ORCHESTRATOR_ANNOUNCEMENT)), OrchestratorAnnouncement
    )


def test_an_announcement_of_an_unknown_provider_kind_is_refused() -> None:
    payload = json.loads(json.dumps(ORCHESTRATOR_ANNOUNCEMENT))
    payload["provider"]["kind"] = "wizard"

    with pytest.raises(ValidationError):
        parse_discovery_message(json.dumps(payload))


def test_a_message_of_an_unknown_type_is_refused() -> None:
    with pytest.raises(ValidationError):
        parse_discovery_message(json.dumps({"type": "gossip"}))


def test_a_worker_announcement_without_its_model_is_refused() -> None:
    payload = json.loads(json.dumps(WORKER_ANNOUNCEMENT))
    del payload["model"]

    with pytest.raises(ValidationError):
        parse_discovery_message(json.dumps(payload))


def test_unknown_fields_are_ignored_so_the_protocol_can_grow() -> None:
    payload = json.loads(json.dumps(WORKER_ANNOUNCEMENT))
    payload["invented_later"] = {"anything": True}
    payload["model"]["invented_later"] = 42

    message = parse_discovery_message(json.dumps(payload))

    assert isinstance(message, WorkerAnnouncement)


def test_a_signature_naming_an_escaping_path_is_refused() -> None:
    # Path validation rides along with the wire contract, so a hostile
    # announcement cannot smuggle one in.
    payload = json.loads(json.dumps(WORKER_ANNOUNCEMENT))
    payload["model"]["signature"]["output"] = ["../../etc/passwd"]

    with pytest.raises(ValidationError):
        parse_discovery_message(json.dumps(payload))


def test_an_announcement_can_be_built_in_code() -> None:
    announcement = WorkerAnnouncement(
        provider=WorkerProvider(name="staff-detector", instance_id=generate_instance_id()),
        model=ModelDescription(
            name="staff-detector",
            version="2026-07-22",
            signature=Signature(input=["image.jpg"], output=["layout.json"]),
            supports_batching=True,
        ),
    )

    # The constant fields do not have to be spelled out to be on the wire.
    assert json.loads(serialize_message(announcement))["type"] == "announcement"
    assert json.loads(serialize_message(announcement))["provider"]["kind"] == "worker"


def test_a_pipeline_with_no_signature_files_is_allowed() -> None:
    announcement = OrchestratorAnnouncement(
        provider=OrchestratorProvider(name="empty", instance_id=generate_instance_id()),
    )

    assert announcement.pipelines == []


def test_instance_ids_are_distinct_per_process() -> None:
    assert len({generate_instance_id() for _ in range(100)}) == 100


def test_the_protocol_constants_match_the_documentation() -> None:
    assert DISCOVERY_EXCHANGE == "musibot.discovery"
    assert DISCOVERY_PROBE_EXCHANGE == "musibot.discovery.probe"
    assert HEARTBEAT_INTERVAL_SECONDS == 10
    assert ENTRY_TTL_SECONDS == 30
