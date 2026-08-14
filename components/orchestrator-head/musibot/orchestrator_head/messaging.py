"""An *Orchestrator Head's* connection to RabbitMQ.

Thin, and a third copy of a shape the `api` service and the *Worker Head* also
have. That duplication is deliberate — see `components/core/README.md`, "This
library performs no I/O", for what it buys and for the trigger that would end
it. What the three must *not* disagree about, the shared queue declarations,
comes from `core` rather than from here.

This one is the union of the other two: an *Orchestrator Head* consumes a shared
work queue like a *Worker Head*, and also requests *Model* work and consumes the
replies like the `api` service does.
"""

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Protocol

import aio_pika
from aio_pika.abc import AbstractExchange, AbstractRobustConnection, ExchangeType
from musibot.core import RabbitSettings
from musibot.core.execution import QueueDeclaration

logger = logging.getLogger(__name__)

MessageHandler = Callable[[bytes], Awaitable[None]]

DEFAULT_EXCHANGE = ""
"""The nameless exchange, which routes to the queue named by the routing key."""


@dataclass
class WorkMessage:
    """A `pipeline-execution-start`, and the means to acknowledge it.

    The acknowledgement is handed to the caller rather than done here because
    *when* to ack is a decision about the work, not about the transport: a
    *Pipeline Execution* is acknowledged the instant it begins running and never
    when it ends, so that an *Orchestrator* that dies mid-execution has its work
    time out rather than redelivered and the *Models* run twice. Until then the
    message stays unacknowledged, which is what keeps the excess in the shared
    queue where another instance can take it.
    """

    body: bytes
    ack: Callable[[], Awaitable[None]]


WorkHandler = Callable[[WorkMessage], Awaitable[None]]


class MessagePublisher(Protocol):
    """What a producer of messages needs, so that the head can be tested
    without RabbitMQ."""

    async def publish(
        self,
        exchange: str,
        routing_key: str,
        body: bytes,
        *,
        expiration_seconds: float | None = None,
        reply_to: str | None = None,
        correlation_id: str | None = None,
    ) -> None: ...


class Broker:
    """A live connection to RabbitMQ, owning two channels."""

    def __init__(self, settings: RabbitSettings):
        self._settings = settings
        self._connection: AbstractRobustConnection | None = None
        self._exchanges: dict[str, AbstractExchange] = {}

    async def connect(self, *, prefetch_count: int = 1) -> None:
        """Open the connection and both channels.

        The work queue gets a **channel of its own**, because a prefetch limit
        applies to a whole channel and this head holds work messages
        unacknowledged while it waits for a free execution slot. Sharing one
        channel would let those unacknowledged messages exhaust the prefetch and
        stop the *Model* results arriving — and the results are what the running
        executions are waiting for, so the head would deadlock against itself.
        """
        self._connection = await aio_pika.connect_robust(
            host=self._settings.rabbit_host,
            port=self._settings.rabbit_port,
            login=self._settings.rabbit_user,
            password=self._settings.rabbit_password.get_secret_value(),
            virtualhost=self._settings.rabbit_vhost,
        )
        self._channel = await self._connection.channel()
        self._work_channel = await self._connection.channel()
        await self._work_channel.set_qos(prefetch_count=prefetch_count)
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
        reply_to: str | None = None,
        correlation_id: str | None = None,
    ) -> None:
        """Publish to a declared exchange, or to the default one when unnamed."""
        message = aio_pika.Message(
            body,
            content_type="application/json",
            delivery_mode=aio_pika.DeliveryMode.NOT_PERSISTENT,
            expiration=expiration_seconds,
            reply_to=reply_to,
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
        work_queue: QueueDeclaration,
        exchange: str,
        routing_key: str,
        handler: WorkHandler,
    ) -> None:
        """Consume the shared work queue for one *Pipeline*.

        One call per *Pipeline* this *Orchestrator* provides, since work is
        addressed to a name and version rather than to an orchestrator. Every
        instance providing that *Pipeline* consumes the same queue and they are
        competing consumers, which is how a *Pipeline* scales horizontally.

        How the queue is declared comes from `core` — every process declaring it
        has to agree, and RabbitMQ refuses the ones that do not.
        """
        if exchange not in self._exchanges:
            await self.declare_exchange(exchange, ExchangeType.DIRECT)

        queue = await self._work_channel.declare_queue(
            work_queue.name,
            exclusive=work_queue.exclusive,
            auto_delete=work_queue.auto_delete,
            durable=work_queue.durable,
        )
        # Bound by exchange *name*: the exchange object above belongs to the
        # other channel, and a binding does not care which channel asks for it.
        await queue.bind(exchange, routing_key=routing_key)

        async def on_message(message: aio_pika.abc.AbstractIncomingMessage) -> None:
            try:
                await handler(WorkMessage(body=message.body, ack=message.ack))
            except Exception:
                logger.exception("Dropping a work message that failed to handle")
                # It may never have been acknowledged, and an unacknowledged
                # message the consumer has given up on would be redelivered to
                # this same head forever.
                await message.ack()

        await queue.consume(on_message)
        logger.info("Consuming %r for routing key %r", work_queue.name, routing_key)

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

    async def declare_reply_queue(self, name: str, handler: MessageHandler) -> None:
        """Consume a queue of this process's own, bound to no exchange.

        Results of the *Model* executions this head requested come back here
        rather than through a shared exchange, because they belong to the one
        requester that asked: the request carries this queue's name as its
        `reply_to`, and a *Worker Head* publishes the result to it through the
        default exchange.
        """
        queue = await self._channel.declare_queue(
            name, exclusive=True, auto_delete=True, durable=False
        )

        async def on_message(message: aio_pika.abc.AbstractIncomingMessage) -> None:
            async with message.process(requeue=False, ignore_processed=True):
                try:
                    await handler(message.body)
                except Exception:
                    logger.exception("Dropping a message that failed to handle on %r", name)

        await queue.consume(on_message)
        logger.info("Consuming the reply queue %r", name)

    async def close(self) -> None:
        if self._connection is not None:
            await self._connection.close()
            logger.info("Disconnected from RabbitMQ")
