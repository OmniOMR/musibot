import json
import logging

import pytest

from musibot.core.config import LoggingSettings
from musibot.core.logging import configure_logging


def test_logs_go_to_standard_output(capsys: pytest.CaptureFixture[str]) -> None:
    configure_logging(LoggingSettings.load(argv=[], env={}))
    logging.getLogger("musibot.test").info("hello")

    captured = capsys.readouterr()
    assert "hello" in captured.out
    assert captured.err == ""


def test_the_log_level_is_honoured(capsys: pytest.CaptureFixture[str]) -> None:
    configure_logging(LoggingSettings.load(argv=["--log-level", "WARNING"], env={}))
    logging.getLogger("musibot.test").info("invisible")
    logging.getLogger("musibot.test").warning("visible")

    captured = capsys.readouterr()
    assert "invisible" not in captured.out
    assert "visible" in captured.out


def test_json_logs_are_one_object_per_line(capsys: pytest.CaptureFixture[str]) -> None:
    configure_logging(LoggingSettings.load(argv=["--log-format", "json"], env={}))
    logging.getLogger("musibot.test").warning("hello")

    line = capsys.readouterr().out.strip()
    record = json.loads(line)
    assert record["level"] == "WARNING"
    assert record["logger"] == "musibot.test"
    assert record["message"] == "hello"


def test_configuring_logging_twice_does_not_duplicate_output(
    capsys: pytest.CaptureFixture[str],
) -> None:
    settings = LoggingSettings.load(argv=[], env={})
    configure_logging(settings)
    configure_logging(settings)

    logging.getLogger("musibot.test").info("once")

    assert capsys.readouterr().out.count("once") == 1
