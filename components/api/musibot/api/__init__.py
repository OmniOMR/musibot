"""The Musibot Web API service."""

from musibot.api.app import create_app
from musibot.api.config import ApiSettings

__all__ = ["ApiSettings", "create_app"]
