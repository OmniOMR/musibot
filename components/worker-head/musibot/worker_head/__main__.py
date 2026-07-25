"""The *Worker Head* entry point: `musibot-worker-head`."""

import asyncio
import logging
import signal
import tempfile
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

from musibot.core import configure_logging

from musibot.worker_head.config import WorkerHeadSettings
from musibot.worker_head.messaging import Broker
from musibot.worker_head.model_process import ModelProcess
from musibot.worker_head.storage import PageStorage
from musibot.worker_head.worker import run_worker

logger = logging.getLogger(__name__)


def head_version() -> str | None:
    """This head's own version, reported in its announcements."""
    try:
        return version("musibot-worker-head")
    except PackageNotFoundError:
        return None


async def serve(settings: WorkerHeadSettings, pages_dir: Path) -> None:
    """Run one *Worker* until it is asked to stop."""
    broker = Broker(settings)
    model = ModelProcess(
        settings.model_command,
        pages_dir,
        ready_timeout_seconds=settings.model_ready_timeout_seconds,
    )
    storage = PageStorage(settings, pages_dir)

    await broker.connect()

    worker = asyncio.create_task(run_worker(broker, model, storage, head_version=head_version()))

    # A stopped Worker says goodbye and shuts its Model down properly, so
    # SIGINT and SIGTERM cancel the task rather than tearing the process down.
    loop = asyncio.get_running_loop()
    for received in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(received, worker.cancel)

    try:
        await worker
    except asyncio.CancelledError:
        logger.info("Stopping")
    finally:
        await model.shutdown()
        await broker.close()


def main() -> None:
    settings = WorkerHeadSettings.load()
    configure_logging(settings)

    logger.info("Starting a Musibot worker head with configuration:\n%s", settings.describe())

    if settings.pages_dir is not None:
        pages_dir = settings.pages_dir
        pages_dir.mkdir(parents=True, exist_ok=True)
        asyncio.run(serve(settings, pages_dir))
        return

    # The mirror is scratch space for the executions this process runs, so when
    # it is not configured it lives in a temporary directory that goes away with
    # the process.
    with tempfile.TemporaryDirectory(prefix="musibot-pages-") as temporary:
        logger.info("Mirroring pages under %s", temporary)
        asyncio.run(serve(settings, Path(temporary)))


if __name__ == "__main__":
    main()
