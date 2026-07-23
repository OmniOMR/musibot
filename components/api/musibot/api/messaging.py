"""The `api` service's connection to RabbitMQ.

Everything the service exchanges with the rest of Musibot travels through here:
it publishes execution requests and consumes results, discovery announcements
and logs. The message *shapes* are defined in `core`; this module only moves
their bytes.

It is deliberately thin. The service is async (FastAPI on one event loop), so
publishing and consuming both happen on that loop with no threads to coordinate,
and aio-pika's robust connection handles reconnection underneath.
"""

import logging
from collections.abc import Awaitable, Callable
from typing import Protocol

import aio_pika
from aio_pika.abc import AbstractExchange, AbstractRobustConnection, ExchangeType
from musibot.core import RabbitSettings

logger = logging.getLogger(__name__)

# A handler is given a raw message body and does something useful with it.
MessageHandler = Callable[[bytes], Awaitable[None]]


class MessagePublisher(Protocol):
    """What a producer of messages needs. Narrow on purpose, so the routes
    depend on this rather than on aio-pika."""

    async def publish(
        self,
        exchange: str,
        routing_key: str,
        body: bytes,
        *,
        expiration_seconds: float | None = None,
    ) -> None: ...


class Broker:
    """A live connection to RabbitMQ, owning one channel.

    Exchanges are declared once (`declare_exchange`) and then referred to by
    name. Nothing here is durable: all of Musibot's state is ephemeral, so a
    broker restart is a system restart.
    """

    def __init__(self, settings: RabbitSettings):
        self._settings = settings
        self._connection: AbstractRobustConnection | None = None
        self._exchanges: dict[str, AbstractExchange] = {}

    async def connect(self) -> None:
        self._connection = await aio_pika.connect_robust(
            host=self._settings.rabbit_host,
            port=self._settings.rabbit_port,
            login=self._settings.rabbit_user,
            password=self._settings.rabbit_password.get_secret_value(),
            virtualhost=self._settings.rabbit_vhost,
        )
        self._channel = await self._connection.channel()
        logger.info(
            "Connected to RabbitMQ at %s:%d", self._settings.rabbit_host, self._settings.rabbit_port
        )

    async def declare_exchange(self, name: str, exchange_type: ExchangeType) -> AbstractExchange:
        """Declare an exchange (idempotent) and remember it for publishing."""
        exchange = await self._channel.declare_exchange(
            name, exchange_type, durable=False, auto_delete=False
        )
        self._exchanges[name] = exchange
        return exchange

    async def publish(
        self,
        exchange: str,
        routing_key: str,
        body: bytes,
        *,
        expiration_seconds: float | None = None,
    ) -> None:
        """Publish a message to a previously declared exchange.

        `expiration_seconds` sets the message's TTL: a request that reaches a
        queue nobody is draining expires rather than being run long after anyone
        cared.
        """
        message = aio_pika.Message(
            body,
            content_type="application/json",
            delivery_mode=aio_pika.DeliveryMode.NOT_PERSISTENT,
            expiration=expiration_seconds,
        )
        await self._exchanges[exchange].publish(message, routing_key=routing_key)

    async def subscribe(
        self,
        *,
        exchange: str,
        exchange_type: ExchangeType,
        handler: MessageHandler,
        routing_key: str = "",
        queue_name: str = "",
    ) -> None:
        """Consume an exchange, calling `handler` with each message body.

        The queue is exclusive and auto-deleting: it belongs to this one service
        instance and vanishes when the instance disconnects, leaving nothing
        behind to accumulate messages. A `handler` that raises is logged and the
        message dropped — a poison message must not wedge the consumer or be
        redelivered forever.
        """
        declared = self._exchanges.get(exchange) or await self.declare_exchange(
            exchange, exchange_type
        )
        queue = await self._channel.declare_queue(
            queue_name, exclusive=True, auto_delete=True, durable=False
        )
        await queue.bind(declared, routing_key=routing_key)

        async def on_message(message: aio_pika.abc.AbstractIncomingMessage) -> None:
            async with message.process(requeue=False, ignore_processed=True):
                try:
                    await handler(message.body)
                except Exception:
                    logger.exception("Dropping a message that failed to handle on %r", exchange)

        await queue.consume(on_message)
        logger.info("Subscribed to exchange %r", exchange)

    async def close(self) -> None:
        if self._connection is not None:
            await self._connection.close()
            logger.info("Disconnected from RabbitMQ")
