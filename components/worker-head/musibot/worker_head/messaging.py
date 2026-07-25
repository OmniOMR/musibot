"""A *Worker Head's* connection to RabbitMQ.

Thin, like the `api` service's counterpart, and separate from it on purpose: a
*Worker Head* is installed next to a *Model*, often into that model's own
virtual environment, so it stays as small as it can be and depends only on
`core`.
"""

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Protocol

import aio_pika
from aio_pika.abc import AbstractExchange, AbstractRobustConnection, ExchangeType
from musibot.core import RabbitSettings

logger = logging.getLogger(__name__)

MessageHandler = Callable[[bytes], Awaitable[None]]


@dataclass
class WorkMessage:
    """A work request, with the AMQP properties that say where to answer.

    Where the result goes is not in the payload — it is `reply_to`, set by
    whoever asked. That is what lets an *Orchestrator Head* and the `api`
    service request the same work and each get its own answer back, without
    either of them appearing in the message a *Model* is asked to run.
    """

    body: bytes
    reply_to: str | None
    correlation_id: str | None


WorkHandler = Callable[[WorkMessage], Awaitable[None]]

DEFAULT_EXCHANGE = ""
"""The nameless exchange, which routes to the queue named by the routing key.
How a result reaches the `reply_to` queue of whoever asked for the work."""


class MessagePublisher(Protocol):
    """What a producer of messages needs, so that the worker can be tested
    without RabbitMQ."""

    async def publish(
        self,
        exchange: str,
        routing_key: str,
        body: bytes,
        *,
        expiration_seconds: float | None = None,
        correlation_id: str | None = None,
    ) -> None: ...


class Broker:
    """A live connection to RabbitMQ, owning one channel."""

    def __init__(self, settings: RabbitSettings):
        self._settings = settings
        self._connection: AbstractRobustConnection | None = None
        self._exchanges: dict[str, AbstractExchange] = {}

    async def connect(self, *, prefetch_count: int = 1) -> None:
        """Open the connection.

        The prefetch is small because a *Model* handles one command at a time:
        holding more messages here would only keep them from a *Worker* that is
        free to run them.
        """
        self._connection = await aio_pika.connect_robust(
            host=self._settings.rabbit_host,
            port=self._settings.rabbit_port,
            login=self._settings.rabbit_user,
            password=self._settings.rabbit_password.get_secret_value(),
            virtualhost=self._settings.rabbit_vhost,
        )
        self._channel = await self._connection.channel()
        await self._channel.set_qos(prefetch_count=prefetch_count)
        logger.info(
            "Connected to RabbitMQ at %s:%d", self._settings.rabbit_host, self._settings.rabbit_port
        )

    async def declare_exchange(self, name: str, exchange_type: ExchangeType) -> AbstractExchange:
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
        correlation_id: str | None = None,
    ) -> None:
        """Publish to a declared exchange, or to the default one when unnamed."""
        message = aio_pika.Message(
            body,
            content_type="application/json",
            delivery_mode=aio_pika.DeliveryMode.NOT_PERSISTENT,
            expiration=expiration_seconds,
            correlation_id=correlation_id,
        )
        target = (
            self._channel.default_exchange
            if exchange == DEFAULT_EXCHANGE
            else self._exchanges[exchange]
        )
        await target.publish(message, routing_key=routing_key)

    async def consume_work(
        self,
        *,
        queue_name: str,
        exchange: str,
        routing_key: str,
        handler: WorkHandler,
    ) -> None:
        """Consume the shared work queue for this *Worker's* one *Model*.

        The queue is named after what it consumes and shared by every *Worker*
        running that model — several of them on it are competing consumers,
        which is exactly how a *Model* scales horizontally. It auto-deletes, so
        a departed *Worker* leaves nothing behind to accumulate messages.

        A message is acknowledged the instant execution begins, never when it
        ends: a *Worker* that crashes mid-execution must not have its work
        redelivered and the model run twice. The execution simply times out
        from the `api` service's point of view instead.

        The queue is declared **durable** even though nothing in Musibot is
        meant to outlive a broker restart: RabbitMQ 4 refuses transient queues
        that are not exclusive, and this one cannot be exclusive precisely
        because it is shared. Durability here costs nothing — the queue still
        auto-deletes with its last consumer, and the messages in it are
        published non-persistent, so a broker restart still loses them.
        """
        declared = self._exchanges.get(exchange) or await self.declare_exchange(
            exchange, ExchangeType.DIRECT
        )
        queue = await self._channel.declare_queue(
            queue_name, exclusive=False, auto_delete=True, durable=True
        )
        await queue.bind(declared, routing_key=routing_key)

        async def on_message(message: aio_pika.abc.AbstractIncomingMessage) -> None:
            await message.ack()
            work = WorkMessage(
                body=message.body,
                reply_to=message.reply_to,
                correlation_id=message.correlation_id,
            )
            try:
                await handler(work)
            except Exception:
                logger.exception("Dropping a work message that failed to handle")

        await queue.consume(on_message)
        logger.info("Consuming %r for routing key %r", queue_name, routing_key)

    async def subscribe(
        self,
        *,
        exchange: str,
        exchange_type: ExchangeType,
        handler: MessageHandler,
    ) -> None:
        """Consume a fanout exchange on a queue belonging to this process alone."""
        declared = self._exchanges.get(exchange) or await self.declare_exchange(
            exchange, exchange_type
        )
        queue = await self._channel.declare_queue("", exclusive=True, auto_delete=True)
        await queue.bind(declared)

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
