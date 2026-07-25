"""What can go wrong, from a *User's* point of view."""


class MusibotError(Exception):
    """Base of every error this client raises."""


class MusibotApiError(MusibotError):
    """The server refused a request.

    Carries the status code, because what a *User* does about it depends on
    which one it was: a `404` after a page was deleted is not a `401`.
    """

    def __init__(self, message: str, *, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


class PipelineNotAvailable(MusibotApiError):
    """No *Orchestrator* or *Worker* provides the requested *Pipeline*.

    Usually a typo in its name or version. `GET /pipelines` — `list_pipelines()`
    here — lists what is actually available.
    """


class PipelineExecutionFailed(MusibotError):
    """The *Pipeline Execution* ran and failed.

    `error` is whatever the *Pipeline* or *Model* said, written for a human.
    """

    def __init__(self, message: str, *, page_id: str, execution_id: int, error: str | None):
        super().__init__(message)
        self.page_id = page_id
        self.execution_id = execution_id
        self.error = error


class PipelineExecutionTimedOut(MusibotError):
    """The client gave up waiting.

    Distinct from the server's own timeout, which fails the execution and is
    reported as :class:`PipelineExecutionFailed`. This one means the client
    stopped watching, and the execution may well still be running.
    """

    def __init__(self, message: str, *, page_id: str, execution_id: int):
        super().__init__(message)
        self.page_id = page_id
        self.execution_id = execution_id
