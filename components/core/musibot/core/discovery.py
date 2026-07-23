"""The discovery protocol: how the `api` service learns what exists.

Every *Orchestrator Head* and *Worker Head* periodically announces what it
provides; the `api` service listens and keeps a registry of what it has heard
about recently. See `docs/discovery.md` for the design, and
`docs/rabbitmq-exchanges-and-messages.md` for where these messages travel.

These are DTOs — they cross a process boundary, arriving as JSON from a service
that may not even be part of this repository, so they are parsed rather than
trusted.
"""

from typing import Annotated, Any, Literal

from pydantic import BaseModel, Discriminator, Tag, TypeAdapter

from musibot.core.identifiers import random_id
from musibot.core.page import PageFilePath

# Exchange names are part of the wire protocol rather than of a deployment, so
# they are constants here rather than settings. Same for the timings below:
# every service has to agree on them, and nothing good comes of one Worker
# announcing on a different schedule from the rest.
DISCOVERY_EXCHANGE = "musibot.discovery"
DISCOVERY_PROBE_EXCHANGE = "musibot.discovery.probe"

HEARTBEAT_INTERVAL_SECONDS = 10
"""How often a head repeats its announcement."""

ENTRY_TTL_SECONDS = 30
"""How long the `api` service keeps a provider it has stopped hearing from."""

PROBE_REPLY_MAX_DELAY_SECONDS = 1.0
"""A reply to a probe waits a random moment, so a hundred Workers do not all
answer in the same instant."""


def generate_instance_id() -> str:
    """Make up the ID identifying one running process, for its whole lifetime."""
    return random_id()


class Signature(BaseModel):
    """The *Files* something reads and the *Files* it produces."""

    input: list[PageFilePath] = []
    output: list[PageFilePath] = []


class PipelineDescription(BaseModel):
    """One *Pipeline* an *Orchestrator* provides."""

    name: str
    version: str
    signature: Signature


class ModelDescription(BaseModel):
    """The one *Model* a *Worker* provides."""

    name: str
    version: str
    signature: Signature
    supports_batching: bool = False


class OrchestratorProvider(BaseModel):
    kind: Literal["orchestrator"] = "orchestrator"
    name: str
    instance_id: str
    head_version: str | None = None


class WorkerProvider(BaseModel):
    kind: Literal["worker"] = "worker"
    name: str
    instance_id: str
    head_version: str | None = None


class OrchestratorAnnouncement(BaseModel):
    """Says: I exist, and these are the Pipelines I run."""

    type: Literal["announcement"] = "announcement"
    provider: OrchestratorProvider
    pipelines: list[PipelineDescription] = []


class WorkerAnnouncement(BaseModel):
    """Says: I exist, and this is the Model I run."""

    type: Literal["announcement"] = "announcement"
    provider: WorkerProvider
    model: ModelDescription


class Goodbye(BaseModel):
    """Says: I am shutting down.

    Sent so the provider drops out of the listing at once, rather than
    lingering for its whole TTL.
    """

    type: Literal["goodbye"] = "goodbye"
    provider: OrchestratorProvider | WorkerProvider


class Probe(BaseModel):
    """Says: everyone announce yourselves now.

    Sent by an `api` service that has just started with an empty registry.
    """

    type: Literal["probe"] = "probe"


def _message_tag(message: Any) -> str | None:
    """Pick the message apart far enough to know which model to parse it as.

    Both announcements carry `"type": "announcement"`, so the kind of provider
    is what tells them apart.
    """
    if isinstance(message, dict):
        message_type = message.get("type")
        provider = message.get("provider")
        provider_kind = provider.get("kind") if isinstance(provider, dict) else None
    else:
        message_type = getattr(message, "type", None)
        provider_kind = getattr(getattr(message, "provider", None), "kind", None)

    if message_type == "announcement":
        return f"announcement:{provider_kind}" if provider_kind else None

    if message_type in ("goodbye", "probe"):
        return str(message_type)

    return None


DiscoveryMessage = Annotated[
    Annotated[OrchestratorAnnouncement, Tag("announcement:orchestrator")]
    | Annotated[WorkerAnnouncement, Tag("announcement:worker")]
    | Annotated[Goodbye, Tag("goodbye")]
    | Annotated[Probe, Tag("probe")],
    Discriminator(_message_tag),
]
"""Any message that may arrive on the discovery exchanges."""

DISCOVERY_MESSAGE_ADAPTER: TypeAdapter[
    OrchestratorAnnouncement | WorkerAnnouncement | Goodbye | Probe
] = TypeAdapter(DiscoveryMessage)


def parse_discovery_message(
    payload: str | bytes,
) -> OrchestratorAnnouncement | WorkerAnnouncement | Goodbye | Probe:
    """Parse a message off the wire, raising `pydantic.ValidationError` if it is
    not one Musibot knows."""
    return DISCOVERY_MESSAGE_ADAPTER.validate_json(payload)


def serialize_message(message: BaseModel) -> bytes:
    """Render a message for the wire."""
    return message.model_dump_json().encode("utf-8")
