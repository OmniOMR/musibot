"""The *Model* subprocess and the IPC that drives it.

This is the whole of what Musibot asks of a *Model*: two pipes carrying JSON
lines, plus a directory of files. See `docs/worker-ipc.md` for the contract; this
module is the head's side of it.

The protocol runs on two dedicated file descriptors rather than on stdin and
stdout, which leaves the *Model's* own output streams free — whatever it prints
is captured here as its log, and a stray `print` cannot corrupt the protocol.
"""

import asyncio
import json
import logging
import os
import shlex
import signal
import subprocess
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

from musibot.core.discovery import ModelDescription
from musibot.core.execution import PipelineExecutionRef
from musibot.core.logs import LogLevel
from pydantic import ValidationError

logger = logging.getLogger(__name__)

IPC_VERSION = 1
"""The protocol version this head speaks. A *Model* announcing another is
refused rather than driven on a guess."""

ModelOutputSink = Callable[[PipelineExecutionRef, str, LogLevel], Awaitable[None]]
"""Where a line the *Model* printed goes, besides this head's own log.

It is given the *Pipeline Execution* the line belongs to, which is knowable here
and nowhere else: a *Model* executes one command at a time, so whatever it
prints belongs to whichever execution holds the lock below.
"""


class ModelFailed(Exception):
    """One execution the *Model* reported as failed, or could not report at all."""


class ModelProtocolError(Exception):
    """The *Model* is not something this head can drive."""


class ModelProcess:
    """One *Model*, running as a child process.

    The model is started once and kept running, because a model that holds
    gigabytes of weights is far too expensive to start per execution. If it dies
    it is restarted on the next execution, and whatever was in flight fails.

    A *Model* does not multitask: one command is sent at a time and nothing
    further goes down the pipe until every execution in it has been reported.
    """

    def __init__(
        self,
        command: str,
        pages_dir: Path,
        *,
        ready_timeout_seconds: float = 300.0,
        stop_timeout_seconds: float = 5.0,
    ):
        self._command = shlex.split(command)
        self._pages_dir = pages_dir
        self._ready_timeout_seconds = ready_timeout_seconds
        # How long each step of stopping is given before the next one: the
        # polite request, then SIGTERM, then SIGKILL.
        self._stop_timeout_seconds = stop_timeout_seconds

        self._process: asyncio.subprocess.Process | None = None
        self._commands: asyncio.StreamWriter | None = None
        self._description: ModelDescription | None = None

        # Where the Model's output goes besides this head's log — the
        # `musibot.logs` exchange, in a running Worker. Set after construction
        # because the WorkerHead that forwards it does not exist until the model
        # has said `ready`, and nothing is lost by that: output printed while a
        # model loads its weights belongs to no execution and could not be
        # attributed to one anyway.
        self.output_sink: ModelOutputSink | None = None
        # Which Pipeline Execution the Model is printing on behalf of. Held here
        # rather than in the WorkerHead because this is where the
        # one-command-at-a-time lock is: two executions may be in flight as far
        # as RabbitMQ is concerned, and only one of them is the model's.
        #
        # It is set when an execution starts and never cleared, so a line read a
        # moment after the model reported is still attributed. Output and
        # reports arrive on two different pipes drained by two different tasks,
        # so a model that prints "done" and then reports completion routinely
        # has that last line read after the report — clearing here would drop
        # exactly the lines a User most wants to see.
        self._attribution: PipelineExecutionRef | None = None

        # Reports arrive on a stream of their own, so the execution that asked
        # for one waits on a future rather than on the pipe.
        self._pending: dict[str, asyncio.Future[None]] = {}
        self._ready: asyncio.Future[ModelDescription] | None = None
        self._readers: list[asyncio.Task[None]] = []
        # Set while shutting down, so that the model exiting — which is the
        # whole point at that moment — is not reported as though something had
        # gone wrong.
        self._stopping = False
        # A Model handles one command at a time, so this lock is the whole of
        # the concurrency control.
        self._lock = asyncio.Lock()

    @property
    def description(self) -> ModelDescription | None:
        """What the *Model* said it is, or None until it has said `ready`.

        The *Model* is the source of truth for its own name, version and
        signature — it is the thing that knows them.
        """
        return self._description

    @property
    def is_running(self) -> bool:
        return self._process is not None and self._process.returncode is None

    async def ensure_running(self) -> ModelDescription:
        """Start the *Model* if it is not running, and wait until it is ready.

        Readiness gates usefully: the head announces nothing and takes no work
        until the model has spoken, so a model spending a minute loading its
        weights is simply not offered any during that minute.
        """
        if self.is_running and self._description is not None:
            return self._description
        self._stopping = False
        return await self._start()

    async def execute(
        self,
        execution_id: str,
        page_id: str,
        input_files: list[str],
        parameters: dict[str, Any],
        pipeline_execution: PipelineExecutionRef | None = None,
    ) -> None:
        """Run one execution and return once the *Model* reports success.

        `pipeline_execution` is who the *Model's* output belongs to while this
        runs; it rides along on the request precisely so that a *Model* need
        never know about it.

        Raises :class:`ModelFailed` if the model reports a failure, or dies
        without reporting anything.
        """
        async with self._lock:
            await self.ensure_running()

            report: asyncio.Future[None] = asyncio.get_running_loop().create_future()
            self._pending[execution_id] = report
            if pipeline_execution is not None:
                self._attribution = pipeline_execution
            try:
                await self._send(
                    {
                        "type": "execute",
                        "execution_id": execution_id,
                        "page": page_id,
                        "input": input_files,
                        "parameters": parameters,
                    }
                )
                await report
            finally:
                self._pending.pop(execution_id, None)

    async def shutdown(self) -> None:
        """Ask the *Model* to stop, then insist.

        The command pipe is closed after the polite request, since reading EOF
        on it means the same thing as `shutdown` — it is what a model sees when
        its head dies.
        """
        process = self._process
        if process is None:
            return

        self._stopping = True

        if process.returncode is None:
            try:
                await self._send({"type": "shutdown"})
            except (ConnectionError, OSError):
                pass  # already gone; nothing to be polite to

        if self._commands is not None:
            self._commands.close()

        if process.returncode is None:
            try:
                await asyncio.wait_for(process.wait(), timeout=self._stop_timeout_seconds)
            except TimeoutError:
                logger.warning("The model ignored shutdown; terminating it")
                self._signal_group(process, signal.SIGTERM)
                try:
                    await asyncio.wait_for(process.wait(), timeout=self._stop_timeout_seconds)
                except TimeoutError:
                    logger.warning("The model ignored SIGTERM; killing it")
                    self._signal_group(process, signal.SIGKILL)
                    await process.wait()

        for reader in self._readers:
            reader.cancel()
        self._readers.clear()
        self._process = None
        self._description = None

    # --- internals -----------------------------------------------------------

    @staticmethod
    def _signal_group(process: asyncio.subprocess.Process, number: int) -> None:
        """Signal the *Model* and everything it started.

        The model leads a process group of its own, so a model that spawns
        workers of its own — a dataloader, say — has them in that group. Sending
        to the group rather than to the one process is what keeps those from
        being left behind, now that the terminal no longer signals them either.
        """
        try:
            os.killpg(process.pid, number)
        except ProcessLookupError:
            pass  # it exited between the timeout expiring and this call

    async def _start(self) -> ModelDescription:
        """Launch the model and wait for it to announce itself."""
        loop = asyncio.get_running_loop()

        # Two pipes, each with one end for us and one for the child. The
        # descriptor numbers are told to the child through the environment
        # rather than fixed at 3 and 4, so that nothing on either side hardcodes
        # them.
        command_read, command_write = os.pipe()
        result_read, result_write = os.pipe()

        environment = dict(os.environ)
        environment["MUSIBOT_IPC_COMMAND_FD"] = str(command_read)
        environment["MUSIBOT_IPC_RESULT_FD"] = str(result_write)
        environment["MUSIBOT_PAGES_DIR"] = str(self._pages_dir)
        # Without this the model's stdout is block-buffered, being a pipe, and
        # its log would reach the User in delayed clumps.
        environment["PYTHONUNBUFFERED"] = "1"

        self._ready = loop.create_future()

        logger.info("Starting the model: %s", " ".join(self._command))
        try:
            process = await asyncio.create_subprocess_exec(
                *self._command,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=environment,
                pass_fds=(command_read, result_write),
                # A session of the model's own. A terminal signals its whole
                # foreground process group, so Ctrl+C on a head started from a
                # shell would otherwise reach the model directly — killing it
                # before this head has asked it to stop, and reporting that as a
                # crash. The model is now stopped deliberately, over the
                # protocol, exactly as it is when the head is signalled alone.
                start_new_session=True,
            )
        finally:
            # The child has its ends now; ours must not stay open or the pipes
            # would never reach EOF.
            os.close(command_read)
            os.close(result_write)

        self._process = process

        transport, protocol = await loop.connect_write_pipe(
            asyncio.streams.FlowControlMixin, os.fdopen(command_write, "wb")
        )
        self._commands = asyncio.StreamWriter(transport, protocol, None, loop)

        results = await self._reader_for(os.fdopen(result_read, "rb"))
        self._readers = [
            asyncio.create_task(self._read_results(results)),
            asyncio.create_task(self._capture_output(process.stdout, logging.INFO, "info")),
            asyncio.create_task(self._capture_output(process.stderr, logging.WARNING, "warning")),
            asyncio.create_task(self._watch_for_exit(process)),
        ]

        try:
            description = await asyncio.wait_for(self._ready, self._ready_timeout_seconds)
        except TimeoutError:
            await self.shutdown()
            raise ModelProtocolError(
                f"The model did not say `ready` within {self._ready_timeout_seconds:.0f}s"
            )

        self._description = description
        logger.info(
            "Model %r version %r is ready (batching: %s)",
            description.name,
            description.version,
            description.supports_batching,
        )
        return description

    async def _reader_for(self, pipe: Any) -> asyncio.StreamReader:
        loop = asyncio.get_running_loop()
        reader = asyncio.StreamReader()
        await loop.connect_read_pipe(lambda: asyncio.StreamReaderProtocol(reader), pipe)
        return reader

    async def _send(self, message: dict[str, Any]) -> None:
        if self._commands is None:
            raise ModelProtocolError("The model is not running")
        self._commands.write((json.dumps(message) + "\n").encode("utf-8"))
        await self._commands.drain()

    async def _read_results(self, results: asyncio.StreamReader) -> None:
        """Dispatch every message the *Model* sends back."""
        while True:
            line = await results.readline()
            if not line:
                return  # EOF: the model is gone, which _watch_for_exit handles

            try:
                message = json.loads(line)
            except json.JSONDecodeError:
                logger.warning("Ignoring an unparsable line from the model: %r", line[:200])
                continue

            self._dispatch(message)

    def _dispatch(self, message: dict[str, Any]) -> None:
        message_type = message.get("type")

        if message_type == "ready":
            self._handle_ready(message)
            return

        if message_type in ("completed", "failed"):
            report = self._pending.get(str(message.get("execution_id")))
            if report is None or report.done():
                logger.warning(
                    "The model reported %r for an execution nobody is waiting on: %r",
                    message_type,
                    message.get("execution_id"),
                )
                return
            if message_type == "completed":
                report.set_result(None)
            else:
                report.set_exception(ModelFailed(str(message.get("error") or "unspecified")))
            return

        # Unknown message types are ignored in both directions, so that the
        # protocol can grow without breaking either side. A `progress` report
        # from a model written against an older head lands here, which is the
        # whole of what happens to it now: an execution takes a second or two,
        # and a model that could report a fraction honestly is the exception.
        logger.debug("Ignoring an unknown message from the model: %r", message_type)

    def _handle_ready(self, message: dict[str, Any]) -> None:
        if self._ready is None or self._ready.done():
            logger.warning("The model said `ready` a second time; ignoring it")
            return

        version = message.get("ipc_version")
        if version != IPC_VERSION:
            self._ready.set_exception(
                ModelProtocolError(
                    f"The model speaks IPC version {version!r}, this head speaks {IPC_VERSION}"
                )
            )
            return

        try:
            self._ready.set_result(ModelDescription.model_validate(message.get("model")))
        except ValidationError as error:
            self._ready.set_exception(
                ModelProtocolError(f"The model announced itself unintelligibly: {error}")
            )

    async def _capture_output(
        self, stream: asyncio.StreamReader | None, level: int, log_level: LogLevel
    ) -> None:
        """Drain the *Model's* stdout or stderr into this head's log, and on
        towards the *User* watching the page.

        Draining is not optional even when nothing is done with the output: a
        pipe nobody reads fills up, and the model then blocks on its next
        `print` — which looks exactly like a model that hangs. That is also why
        a sink that raises is swallowed here: a broker that has gone away must
        not stop this loop reading.
        """
        if stream is None:
            return
        while True:
            line = await stream.readline()
            if not line:
                return
            text = line.decode("utf-8", "replace").rstrip()
            logger.log(level, "[model] %s", text)

            sink, attribution = self.output_sink, self._attribution
            if sink is None or attribution is None:
                # Nothing is running, so this line belongs to no execution —
                # a startup banner, or something printed after the report.
                continue
            try:
                await sink(attribution, text, log_level)
            except Exception:
                logger.warning("Could not forward a line of the model's output", exc_info=True)

    async def _watch_for_exit(self, process: asyncio.subprocess.Process) -> None:
        """Fail whatever is in flight when the *Model* dies.

        A dead model fails its work, which propagates up and fails the *Pipeline
        Execution*. The model is restarted by the next execution that needs it.
        """
        returncode = await process.wait()

        if self._stopping:
            logger.info("The model stopped with code %s", returncode)
        else:
            # Unasked-for, so whatever it was running has just failed.
            logger.warning("The model exited unexpectedly with code %s", returncode)

        if self._ready is not None and not self._ready.done():
            self._ready.set_exception(
                ModelProtocolError(f"The model exited before saying `ready` (code {returncode})")
            )

        for execution_id, report in list(self._pending.items()):
            if not report.done():
                report.set_exception(
                    ModelFailed(f"The model exited without reporting (code {returncode})")
                )
            self._pending.pop(execution_id, None)

        self._description = None
