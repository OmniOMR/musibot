"""Logging setup shared by all Musibot services."""

import json
import logging
import sys

from musibot.core.config import LoggingSettings

TEXT_FORMAT = "%(asctime)s %(levelname)-8s %(name)s: %(message)s"


class JsonFormatter(logging.Formatter):
    """Renders each log record as one JSON object on one line."""

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "time": self.formatTime(record),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload)


def configure_logging(settings: LoggingSettings) -> None:
    """Set up logging for a Musibot service, according to its settings.

    Logs go to standard output. No Musibot service writes anything else there —
    a *Model* speaks over its own pipes and never uses this package at all — so
    the stream is free, and both systemd and docker capture it as the service's
    log without further arrangement.
    """
    handler = logging.StreamHandler(sys.stdout)

    if settings.log_format == "json":
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(logging.Formatter(TEXT_FORMAT))

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(settings.log_level)
