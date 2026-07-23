"""Broker tests against a real RabbitMQ — the one from the local dev stack.

Skipped when RabbitMQ is not reachable, so the ordinary `pytest` run stays
hermetic; run `docker compose up` in `/deploy` to exercise these.
"""

import asyncio
import socket

import pytest
from aio_pika.abc import ExchangeType

from musibot.api.config import ApiSettings
from musibot.api.messaging import Broker


def rabbitmq_is_up() -> bool:
    try:
        with socket.create_connection(("localhost", 5672), timeout=0.5):
            return True
    except OSError:
        return False


pytestmark = pytest.mark.skipif(not rabbitmq_is_up(), reason="RabbitMQ is not running")

TEST_EXCHANGE = "musibot.test-broker"


async def with_broker() -> Broker:
    broker = Broker(ApiSettings.for_testing())
    await broker.connect()
    return broker


def test_a_published_message_reaches_a_subscriber() -> None:
    async def scenario() -> None:
        broker = await with_broker()
        received: asyncio.Queue[bytes] = asyncio.Queue()

        await broker.declare_exchange(TEST_EXCHANGE, ExchangeType.FANOUT)
        await broker.subscribe(
            exchange=TEST_EXCHANGE, exchange_type=ExchangeType.FANOUT, handler=received.put
        )

        await broker.publish(TEST_EXCHANGE, "", b'{"hello": "world"}')

        body = await asyncio.wait_for(received.get(), timeout=5)
        assert body == b'{"hello": "world"}'

        await broker.close()

    asyncio.run(scenario())


def test_direct_routing_delivers_only_matching_keys() -> None:
    async def scenario() -> None:
        broker = await with_broker()
        received: asyncio.Queue[bytes] = asyncio.Queue()

        await broker.declare_exchange(TEST_EXCHANGE + ".direct", ExchangeType.DIRECT)
        await broker.subscribe(
            exchange=TEST_EXCHANGE + ".direct",
            exchange_type=ExchangeType.DIRECT,
            handler=received.put,
            routing_key="wanted@1.0.0",
        )

        await broker.publish(TEST_EXCHANGE + ".direct", "unwanted@1.0.0", b"no")
        await broker.publish(TEST_EXCHANGE + ".direct", "wanted@1.0.0", b"yes")

        body = await asyncio.wait_for(received.get(), timeout=5)
        assert body == b"yes"  # the unwanted key never arrived

        await broker.close()

    asyncio.run(scenario())


def test_a_handler_that_raises_does_not_stop_the_consumer() -> None:
    async def scenario() -> None:
        broker = await with_broker()
        seen: list[bytes] = []

        async def handler(body: bytes) -> None:
            seen.append(body)
            if body == b"boom":
                raise RuntimeError("handler failed on purpose")

        await broker.declare_exchange(TEST_EXCHANGE + ".resilient", ExchangeType.FANOUT)
        await broker.subscribe(
            exchange=TEST_EXCHANGE + ".resilient",
            exchange_type=ExchangeType.FANOUT,
            handler=handler,
        )

        await broker.publish(TEST_EXCHANGE + ".resilient", "", b"boom")
        await broker.publish(TEST_EXCHANGE + ".resilient", "", b"after")

        for _ in range(50):
            if b"after" in seen:
                break
            await asyncio.sleep(0.05)

        assert b"boom" in seen and b"after" in seen  # survived the failure

        await broker.close()

    asyncio.run(scenario())
