"""The provider registry: what it remembers, forgets, and warns about."""

import asyncio

from musibot.core.discovery import (
    Goodbye,
    ModelDescription,
    OrchestratorAnnouncement,
    OrchestratorProvider,
    PipelineDescription,
    Signature,
    WorkerAnnouncement,
    WorkerProvider,
    serialize_message,
)

from musibot.api.discovery import ProviderRegistry


class FakeClock:
    """A clock a test moves by hand, so a TTL can expire without waiting."""

    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def orchestrator_announcement(
    *,
    name: str = "reference-orchestrator",
    instance_id: str = "orchestrator-1",
    pipeline_name: str = "hello-world",
    version: str = "1.0.0",
    signature: Signature | None = None,
) -> OrchestratorAnnouncement:
    return OrchestratorAnnouncement(
        provider=OrchestratorProvider(name=name, instance_id=instance_id),
        pipelines=[
            PipelineDescription(
                name=pipeline_name,
                version=version,
                signature=signature
                or Signature(input=["image.jpg"], output=["transcription.musicxml"]),
            )
        ],
    )


def worker_announcement(
    *,
    instance_id: str = "worker-1",
    model_name: str = "staff-detector",
    version: str = "2026-07-22",
    signature: Signature | None = None,
) -> WorkerAnnouncement:
    return WorkerAnnouncement(
        provider=WorkerProvider(name=model_name, instance_id=instance_id),
        model=ModelDescription(
            name=model_name,
            version=version,
            signature=signature or Signature(input=["image.jpg"], output=["layout.json"]),
            supports_batching=True,
        ),
    )


def test_an_announced_pipeline_is_listed() -> None:
    registry = ProviderRegistry()
    registry.record(orchestrator_announcement())

    listing = registry.listing()

    assert len(listing.pipelines) == 1
    entry = listing.pipelines[0]
    assert (entry.name, entry.version) == ("hello-world", "1.0.0")
    assert entry.implicit is False
    assert entry.orchestrators == ["reference-orchestrator"]
    assert entry.instances == 1
    assert listing.warnings == []


def test_an_announced_model_yields_an_implicit_pipeline() -> None:
    registry = ProviderRegistry()
    registry.record(worker_announcement())

    entry = registry.listing().pipelines[0]

    assert (entry.name, entry.version) == ("staff-detector", "2026-07-22")
    assert entry.implicit is True
    assert entry.orchestrators == []
    assert entry.signature.output == ["layout.json"]


def test_instances_of_the_same_pipeline_collapse_into_one_entry() -> None:
    registry = ProviderRegistry()
    registry.record(orchestrator_announcement(instance_id="orchestrator-1"))
    registry.record(orchestrator_announcement(instance_id="orchestrator-2"))

    listing = registry.listing()

    assert len(listing.pipelines) == 1
    assert listing.pipelines[0].instances == 2
    assert listing.warnings == []


def test_a_repeated_announcement_is_not_counted_twice() -> None:
    registry = ProviderRegistry()
    registry.record(orchestrator_announcement())
    registry.record(orchestrator_announcement())

    assert registry.listing().pipelines[0].instances == 1


def test_a_provider_is_dropped_once_its_ttl_passes() -> None:
    clock = FakeClock()
    registry = ProviderRegistry(ttl_seconds=30, clock=clock)
    registry.record(orchestrator_announcement())

    clock.advance(29)
    assert len(registry.listing().pipelines) == 1

    clock.advance(2)
    assert registry.listing().pipelines == []


def test_a_heartbeat_keeps_a_provider_alive() -> None:
    clock = FakeClock()
    registry = ProviderRegistry(ttl_seconds=30, clock=clock)
    registry.record(orchestrator_announcement())

    for _ in range(10):
        clock.advance(10)
        registry.record(orchestrator_announcement())

    assert len(registry.listing().pipelines) == 1


def test_a_goodbye_drops_a_provider_at_once() -> None:
    registry = ProviderRegistry()
    registry.record(worker_announcement(instance_id="worker-1"))

    async def scenario() -> None:
        await registry.handle_message(
            serialize_message(
                Goodbye(provider=WorkerProvider(name="staff-detector", instance_id="worker-1"))
            )
        )

    asyncio.run(scenario())

    assert registry.listing().pipelines == []


def test_announcements_are_taken_off_the_wire() -> None:
    registry = ProviderRegistry()

    async def scenario() -> None:
        await registry.handle_message(serialize_message(orchestrator_announcement()))
        await registry.handle_message(serialize_message(worker_announcement()))

    asyncio.run(scenario())

    assert [entry.name for entry in registry.listing().pipelines] == [
        "hello-world",
        "staff-detector",
    ]


def test_differing_signatures_for_one_pipeline_are_reported() -> None:
    registry = ProviderRegistry()
    registry.record(orchestrator_announcement(name="reference-orchestrator"))
    registry.record(
        orchestrator_announcement(
            name="my-laptop-orchestrator",
            instance_id="orchestrator-2",
            signature=Signature(input=["image.jpg"], output=["layout.json"]),
        )
    )

    listing = registry.listing()

    assert len(listing.pipelines) == 1
    assert [warning.type for warning in listing.warnings] == ["conflicting-signatures"]
    assert "reference-orchestrator" in listing.warnings[0].message
    assert "my-laptop-orchestrator" in listing.warnings[0].message


def test_the_same_signature_in_a_different_order_is_not_a_conflict() -> None:
    registry = ProviderRegistry()
    both = Signature(input=["image.jpg", "layout.json"], output=["transcription.musicxml"])
    reversed_order = Signature(
        input=["layout.json", "image.jpg"], output=["transcription.musicxml"]
    )
    registry.record(orchestrator_announcement(signature=both))
    registry.record(
        orchestrator_announcement(
            name="my-laptop-orchestrator", instance_id="orchestrator-2", signature=reversed_order
        )
    )

    assert registry.listing().warnings == []


def test_a_pipeline_colliding_with_a_model_suppresses_the_implicit_one() -> None:
    registry = ProviderRegistry()
    registry.record(orchestrator_announcement(pipeline_name="staff-detector", version="2026-07-22"))
    registry.record(worker_announcement(model_name="staff-detector", version="2026-07-22"))

    listing = registry.listing()

    assert len(listing.pipelines) == 1
    assert listing.pipelines[0].implicit is False
    assert [warning.type for warning in listing.warnings] == ["name-collision"]


def test_the_same_name_at_a_different_version_is_not_a_collision() -> None:
    registry = ProviderRegistry()
    registry.record(orchestrator_announcement(pipeline_name="staff-detector", version="1.0.0"))
    registry.record(worker_announcement(model_name="staff-detector", version="2026-07-22"))

    listing = registry.listing()

    assert len(listing.pipelines) == 2
    assert listing.warnings == []


def test_a_model_is_found_by_name_and_version() -> None:
    registry = ProviderRegistry()
    registry.record(worker_announcement())

    found = registry.find_model("staff-detector", "2026-07-22")

    assert found is not None
    assert found.signature.input == ["image.jpg"]
    assert registry.find_model("staff-detector", "1.0.0") is None
    assert registry.find_model("nothing-like-this", "2026-07-22") is None


def test_a_pipeline_is_found_by_name_and_version() -> None:
    registry = ProviderRegistry()
    registry.record(orchestrator_announcement())

    assert registry.provides_pipeline("hello-world", "1.0.0") is True
    assert registry.provides_pipeline("hello-world", "2.0.0") is False


def test_an_expired_model_is_no_longer_found() -> None:
    clock = FakeClock()
    registry = ProviderRegistry(ttl_seconds=30, clock=clock)
    registry.record(worker_announcement())

    clock.advance(31)

    assert registry.find_model("staff-detector", "2026-07-22") is None
