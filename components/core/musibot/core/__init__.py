"""Shared library and wire contract for the Musibot software system."""

from musibot.core.config import (
    ENV_PREFIX,
    LoggingSettings,
    MusibotSettings,
    RabbitSettings,
    S3Settings,
)
from musibot.core.logging import configure_logging
from musibot.core.page import (
    InvalidFilePath,
    InvalidPageId,
    PageFilePath,
    PageId,
    generate_page_id,
    local_path,
    object_key,
    object_prefix,
    validate_file_path,
    validate_page_id,
)

__all__ = [
    "ENV_PREFIX",
    "InvalidFilePath",
    "InvalidPageId",
    "LoggingSettings",
    "MusibotSettings",
    "PageFilePath",
    "PageId",
    "RabbitSettings",
    "S3Settings",
    "configure_logging",
    "generate_page_id",
    "local_path",
    "object_key",
    "object_prefix",
    "validate_file_path",
    "validate_page_id",
]
