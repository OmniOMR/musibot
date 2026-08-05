"""Test doubles for the service's external collaborators."""

from dataclasses import dataclass
from datetime import UTC, datetime

from musibot.api.storage import HttpMethod, StoredFile

# Every file the fake holds is stamped with this. Nothing under test reads a
# timestamp for its meaning — it exists so a poller can tell a rewritten *File*
# from an untouched one — so one fixed instant keeps the fake deterministic.
FAKE_MTIME = datetime(2026, 1, 1, tzinfo=UTC)


class FakeStorage:
    """A `StoragePort` that signs nothing and reaches no network.

    It returns deterministic, inspectable URLs and records what it was asked to
    delete, so the endpoints can be tested without boto3 or a live MinIO.
    """

    def __init__(self) -> None:
        self.deleted_pages: list[str] = []
        self.wiped = False
        # What each page is pretending to hold, as path to size. A test fills
        # this through `put` to stand in for bytes that went straight to MinIO,
        # which this service never sees and can only ask about afterwards.
        self.files: dict[str, dict[str, int]] = {}

    def put(self, page_id: str, file_path: str, size: int = 1) -> None:
        """Pretend a *User* or a *Worker* wrote one *File* of a page."""
        self.files.setdefault(page_id, {})[file_path] = size

    def presign(self, page_id: str, file_path: str, method: HttpMethod, ttl_seconds: float) -> str:
        return f"https://minio.test/{page_id}/{file_path}?method={method}&ttl={int(ttl_seconds)}"

    def list_page_files(self, page_id: str) -> list[StoredFile]:
        # Sorted by path, as a real listing is sorted by key.
        return [
            StoredFile(path=path, size=size, last_modified=FAKE_MTIME)
            for path, size in sorted(self.files.get(page_id, {}).items())
        ]

    def delete_page(self, page_id: str) -> None:
        self.deleted_pages.append(page_id)
        self.files.pop(page_id, None)

    def wipe_bucket(self) -> None:
        self.wiped = True
        self.files.clear()

    def page_sizes(self) -> dict[str, int]:
        return {page_id: sum(files.values()) for page_id, files in self.files.items()}


@dataclass
class PublishedMessage:
    exchange: str
    routing_key: str
    body: bytes
    expiration_seconds: float | None
    reply_to: str | None = None
    correlation_id: str | None = None


class FakePublisher:
    """A `MessagePublisher` that records what it was asked to publish, so the
    routes and the execution service can be tested without RabbitMQ."""

    def __init__(self) -> None:
        self.published: list[PublishedMessage] = []

    async def publish(
        self,
        exchange: str,
        routing_key: str,
        body: bytes,
        *,
        expiration_seconds: float | None = None,
        reply_to: str | None = None,
        correlation_id: str | None = None,
    ) -> None:
        self.published.append(
            PublishedMessage(
                exchange, routing_key, body, expiration_seconds, reply_to, correlation_id
            )
        )

    def only(self, exchange: str) -> PublishedMessage:
        """The one message published to an exchange, asserting there was one."""
        matching = [message for message in self.published if message.exchange == exchange]
        assert len(matching) == 1, f"expected one message on {exchange!r}, got {len(matching)}"
        return matching[0]
