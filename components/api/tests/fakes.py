"""Test doubles for the service's external collaborators."""

from dataclasses import dataclass

from musibot.api.storage import HttpMethod


class FakeStorage:
    """A `StoragePort` that signs nothing and reaches no network.

    It returns deterministic, inspectable URLs and records what it was asked to
    delete, so the endpoints can be tested without boto3 or a live MinIO.
    """

    def __init__(self) -> None:
        self.deleted_pages: list[str] = []
        self.wiped = False

    def presign(self, page_id: str, file_path: str, method: HttpMethod, ttl_seconds: float) -> str:
        return f"https://minio.test/{page_id}/{file_path}?method={method}&ttl={int(ttl_seconds)}"

    def delete_page(self, page_id: str) -> None:
        self.deleted_pages.append(page_id)

    def wipe_bucket(self) -> None:
        self.wiped = True


@dataclass
class PublishedMessage:
    exchange: str
    routing_key: str
    body: bytes
    expiration_seconds: float | None


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
    ) -> None:
        self.published.append(PublishedMessage(exchange, routing_key, body, expiration_seconds))
