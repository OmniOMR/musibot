"""The `api` service entry point: `musibot-api` / `python -m musibot.api`."""

import logging

import uvicorn
from musibot.core import configure_logging

from musibot.api.app import create_app
from musibot.api.config import ApiSettings

logger = logging.getLogger(__name__)


def main() -> None:
    settings = ApiSettings.load()
    configure_logging(settings)

    logger.info("Starting Musibot API with configuration:\n%s", settings.describe())

    app = create_app(settings)
    uvicorn.run(app, host=settings.host, port=settings.port, log_config=None)


if __name__ == "__main__":
    main()
