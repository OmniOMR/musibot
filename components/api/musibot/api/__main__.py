"""The `api` service entry point: `musibot-api` / `python -m musibot.api`."""

import logging

import uvicorn
from musibot.core import configure_logging

from musibot.api.app import create_app
from musibot.api.config import ApiSettings
from musibot.api.messaging import Broker
from musibot.api.storage import Storage

logger = logging.getLogger(__name__)


def main() -> None:
    settings = ApiSettings.load()
    configure_logging(settings)

    logger.info("Starting Musibot API with configuration:\n%s", settings.describe())

    # The service's state is ephemeral and starts empty, so any objects MinIO
    # still holds are stale and must be cleared before the service accepts work.
    storage = Storage(settings)
    storage.wipe_bucket()

    # The broker is both the publisher the routes use and the connection the
    # lifespan opens and subscribes the results consumer on.
    broker = Broker(settings)

    app = create_app(settings, storage=storage, publisher=broker, broker=broker)
    uvicorn.run(app, host=settings.host, port=settings.port, log_config=None)


if __name__ == "__main__":
    main()
