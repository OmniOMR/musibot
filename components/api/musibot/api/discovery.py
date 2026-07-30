"""The registry of what currently exists: *Pipelines* and *Models*.

Nothing tells the `api` service what is deployed — *Orchestrators* and *Workers*
are plugged into a running system just by connecting to RabbitMQ. Instead every
head announces what it provides, this service listens, and what it has heard
from recently is what it believes exists. See `docs/discovery.md`.

The registry is a directory that expires, not a service registry. It is never
used to route work — that is RabbitMQ's job — only to answer `GET /pipelines`
and to reject a *Pipeline* nobody provides. Being a few seconds out of date is
therefore harmless and expected.

These are internal domain objects assembled from already-parsed announcements,
so they are dataclasses; the DTOs that cross the HTTP boundary live in
`schemas.py` and the ones that cross RabbitMQ live in `core`.
"""

import logging
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Literal

from musibot.core.discovery import (
    ENTRY_TTL_SECONDS,
    Goodbye,
    ModelDescription,
    OrchestratorAnnouncement,
    PipelineDescription,
    Signature,
    WorkerAnnouncement,
    parse_discovery_message,
)

logger = logging.getLogger(__name__)

Announcement = OrchestratorAnnouncement | WorkerAnnouncement

WarningType = Literal["conflicting-signatures", "name-collision"]


@dataclass
class ProviderEntry:
    """One announcing process, and when it was last heard from."""

    announcement: Announcement
    last_seen: float


@dataclass
class PipelineListing:
    """One entry of the *Pipeline* listing.

    Several instances announcing the same name and version are the
    horizontal-scaling case and collapse into one of these.
    """

    name: str
    version: str
    signature: Signature
    implicit: bool
    orchestrators: list[str]
    instances: int


@dataclass
class DiscoveryWarning:
    """Something an operator got wrong, reported rather than resolved.

    Surfaced over HTTP as well as logged: the person who causes one is typically
    a *Model developer* with an in-development *Orchestrator* plugged into a
    shared system, and no access to this service's log.
    """

    type: WarningType
    message: str
    name: str
    version: str


@dataclass
class Listing:
    """Everything `GET /pipelines` answers with."""

    pipelines: list[PipelineListing]
    warnings: list[DiscoveryWarning]


@dataclass
class _PipelineGroup:
    """The *Pipeline* announcements collected under one name and version."""

    signature: Signature
    # The orchestrator whose signature was taken as the entry's, so that a
    # conflicting one can be reported against it by name.
    signature_owner: str
    orchestrators: set[str] = field(default_factory=set)
    instances: int = 0
    conflicting_orchestrator: str | None = None


@dataclass
class _ModelGroup:
    """The *Model* announcements collected under one name and version."""

    model: ModelDescription
    instances: int = 0


def _signature_key(signature: Signature) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Compare signatures by what they name, not by the order they name it in."""
    return tuple(sorted(signature.input)), tuple(sorted(signature.output))


class ProviderRegistry:
    """What the service has heard about recently.

    Entries are keyed by `instance_id`, so several instances of the same
    *Orchestrator* or *Model* are tracked separately — that count is what the
    listing reports as `instances`.

    Guarded by a lock: announcements arrive on the event loop while the HTTP
    endpoints read the registry from the threadpool.
    """

    def __init__(
        self,
        *,
        ttl_seconds: float = ENTRY_TTL_SECONDS,
        clock: Callable[[], float] = time.monotonic,
    ):
        self._entries: dict[str, ProviderEntry] = {}
        self._ttl_seconds = ttl_seconds
        self._clock = clock
        self._lock = threading.Lock()

    # --- taking messages in --------------------------------------------------

    async def handle_message(self, body: bytes) -> None:
        """Fold one message off the discovery exchange into the registry."""
        message = parse_discovery_message(body)

        if isinstance(message, OrchestratorAnnouncement | WorkerAnnouncement):
            self.record(message)
        elif isinstance(message, Goodbye):
            self.forget(message.provider.instance_id)
        # A Probe is this service's own doing and travels on the other exchange;
        # one arriving here is not ours to act on.

    def record(self, announcement: Announcement) -> None:
        """Note that a provider exists, or that it still does."""
        with self._lock:
            instance_id = announcement.provider.instance_id
            if instance_id not in self._entries:
                logger.info(
                    "Discovered %s %r (instance %s)",
                    announcement.provider.kind,
                    announcement.provider.name,
                    instance_id,
                )
            self._entries[instance_id] = ProviderEntry(announcement, self._clock())
            self._drop_expired()

    def forget(self, instance_id: str) -> None:
        """Drop a provider that said goodbye, rather than waiting out its TTL."""
        with self._lock:
            entry = self._entries.pop(instance_id, None)
            if entry is not None:
                logger.info(
                    "Provider %r (instance %s) said goodbye",
                    entry.announcement.provider.name,
                    instance_id,
                )

    # --- answering questions -------------------------------------------------

    def live_entries(self) -> list[ProviderEntry]:
        """Every provider heard from within the TTL."""
        with self._lock:
            self._drop_expired()
            return list(self._entries.values())

    def find_model(self, name: str, version: str) -> ModelDescription | None:
        """The *Model* announced under this name and version, if one is live.

        Any live announcer of it will do — they are all claiming to be the same
        *Model*, and the answer is used to describe the work, never to address
        it at a particular *Worker*.
        """
        for entry in self.live_entries():
            announcement = entry.announcement
            if (
                isinstance(announcement, WorkerAnnouncement)
                and announcement.model.name == name
                and announcement.model.version == version
            ):
                return announcement.model
        return None

    def find_pipeline(self, name: str, version: str) -> PipelineDescription | None:
        """The *Pipeline* announced under this name and version, if one is live.

        Any live announcer of it will do, as with `find_model` — and where two
        of them disagree about the *Signature*, the listing says so as a
        `conflicting-signatures` warning rather than this picking a winner.
        """
        for entry in self.live_entries():
            announcement = entry.announcement
            if isinstance(announcement, OrchestratorAnnouncement):
                for pipeline in announcement.pipelines:
                    if pipeline.name == name and pipeline.version == version:
                        return pipeline
        return None

    def provides_pipeline(self, name: str, version: str) -> bool:
        """Whether some *Orchestrator* announces this *Pipeline*."""
        return self.find_pipeline(name, version) is not None

    def listing(self) -> Listing:
        """Derive the *Pipeline* listing, *ImplicitPipelines* and warnings included."""
        pipelines, models = self._group(self.live_entries())

        entries: list[PipelineListing] = []
        warnings: list[DiscoveryWarning] = []

        for (name, version), group in pipelines.items():
            entries.append(
                PipelineListing(
                    name=name,
                    version=version,
                    signature=group.signature,
                    implicit=False,
                    orchestrators=sorted(group.orchestrators),
                    instances=group.instances,
                )
            )
            if group.conflicting_orchestrator is not None:
                warnings.append(
                    DiscoveryWarning(
                        type="conflicting-signatures",
                        message=(
                            f"Pipeline {name!r} version {version!r} is announced with "
                            f"differing signatures by orchestrators "
                            f"{group.signature_owner!r} and {group.conflicting_orchestrator!r}."
                        ),
                        name=name,
                        version=version,
                    )
                )

        for (name, version), model_group in models.items():
            # An explicit Pipeline wins the entry; the ImplicitPipeline behind
            # the colliding Model is suppressed. Detected on name *and* version,
            # since that pair is what a User asks for and what would otherwise be
            # ambiguous.
            colliding = pipelines.get((name, version))
            if colliding is not None:
                warnings.append(
                    DiscoveryWarning(
                        type="name-collision",
                        message=(
                            f"Pipeline {name!r} version {version!r} from orchestrator "
                            f"{colliding.signature_owner!r} collides with a model of the same "
                            f"name and version; the implicit pipeline for that model is "
                            f"suppressed."
                        ),
                        name=name,
                        version=version,
                    )
                )
                continue

            entries.append(
                PipelineListing(
                    name=name,
                    version=version,
                    signature=model_group.model.signature,
                    implicit=True,
                    orchestrators=[],
                    instances=model_group.instances,
                )
            )

        entries.sort(key=lambda entry: (entry.name, entry.version))
        warnings.sort(key=lambda warning: (warning.name, warning.version, warning.type))

        for warning in warnings:
            logger.warning("%s", warning.message)

        return Listing(pipelines=entries, warnings=warnings)

    # --- internals -----------------------------------------------------------

    def _group(
        self, entries: list[ProviderEntry]
    ) -> tuple[dict[tuple[str, str], _PipelineGroup], dict[tuple[str, str], _ModelGroup]]:
        """Collect announcements by what they announce, rather than by who did."""
        pipelines: dict[tuple[str, str], _PipelineGroup] = {}
        models: dict[tuple[str, str], _ModelGroup] = {}

        for entry in entries:
            announcement = entry.announcement

            if isinstance(announcement, OrchestratorAnnouncement):
                orchestrator = announcement.provider.name
                for pipeline in announcement.pipelines:
                    key = (pipeline.name, pipeline.version)
                    group = pipelines.get(key)
                    if group is None:
                        group = _PipelineGroup(
                            signature=pipeline.signature, signature_owner=orchestrator
                        )
                        pipelines[key] = group
                    elif (
                        group.conflicting_orchestrator is None
                        and orchestrator != group.signature_owner
                        and _signature_key(pipeline.signature) != _signature_key(group.signature)
                    ):
                        # Identical signatures are the horizontal-scaling case;
                        # differing ones cannot be.
                        group.conflicting_orchestrator = orchestrator
                    group.orchestrators.add(orchestrator)
                    group.instances += 1
            else:
                model = announcement.model
                key = (model.name, model.version)
                model_group = models.get(key)
                if model_group is None:
                    model_group = _ModelGroup(model=model)
                    models[key] = model_group
                model_group.instances += 1

        return pipelines, models

    def _drop_expired(self) -> None:
        """Forget providers not heard from within the TTL. Caller holds the lock."""
        deadline = self._clock() - self._ttl_seconds
        expired = [
            instance_id
            for instance_id, entry in self._entries.items()
            if entry.last_seen < deadline
        ]
        for instance_id in expired:
            entry = self._entries.pop(instance_id)
            logger.info(
                "Provider %r (instance %s) went silent and was dropped",
                entry.announcement.provider.name,
                instance_id,
            )
