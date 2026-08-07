"""The local mirror of MinIO that a *Model* reads and writes.

A *Model* never speaks to object storage. Before a command, this module brings
that command's declared input *Files* down into a directory laid out exactly
like the bucket; after it, it sends back whatever the model created or changed.
Between those two moments the model works with ordinary local files.

Paths coming back from a *Model* are checked against `musibot.core.page`, which
refuses anything that could leave the page's own folder — symbolic links
included, since a model is free to create those.
"""

import logging
import shutil
from pathlib import Path
from typing import TYPE_CHECKING, Protocol

import boto3
from botocore.client import Config
from botocore.exceptions import ClientError
from musibot.core import S3Settings, local_path, validate_page_id
from musibot.core.page import InvalidFilePath

if TYPE_CHECKING:
    # Type stubs only. They come from `boto3-stubs[s3]`, which is a *dev*
    # dependency and is therefore absent beside a deployed worker — so
    # importing this at module scope crashes the process on startup, and does
    # it only in production, because every development environment has the
    # stubs installed and nothing local ever notices.
    #
    # The one annotation using it needs no quotes: it sits in a function body,
    # and those are never evaluated. A *signature* annotation would need them,
    # which is why the `api` service's copy of this quotes its return type.
    from mypy_boto3_s3.client import S3Client

logger = logging.getLogger(__name__)

FileStamp = tuple[int, int]
"""How a file looked at a moment: its size and its modification time."""


class InputFileMissing(Exception):
    """A *File* the execution declared as input is not in object storage.

    Reported as a failed execution with this message rather than left to the
    *Model*, which could only say "no such file" without knowing why.
    """


class PageStoragePort(Protocol):
    """What the worker needs of object storage.

    A `Protocol` so a test can supply a fake without boto3 or a live MinIO.
    """

    def stage_inputs(self, page_id: str, file_paths: list[str]) -> None: ...

    def snapshot(self, page_id: str) -> dict[str, FileStamp]: ...

    def upload_changes(self, page_id: str, before: dict[str, FileStamp]) -> list[str]: ...

    def discard(self, page_id: str) -> None: ...


class PageStorage:
    """The bucket holding every *Musicorpus Page*, and its local mirror.

    Every call here is blocking boto3, so callers run them off the event loop.
    """

    def __init__(self, settings: S3Settings, pages_dir: Path):
        self._bucket = settings.s3_bucket
        self._pages_dir = pages_dir

        # Where in the bucket this deployment keeps its pages. It must match
        # what the `api` service was configured with: a Worker Head rooted
        # differently would stage nothing and upload where nobody looks, and
        # both halves of that fail quietly.
        self._layout = settings.object_layout
        self._client: S3Client = boto3.client(
            "s3",
            endpoint_url=settings.s3_endpoint_url,
            aws_access_key_id=settings.s3_access_key,
            aws_secret_access_key=settings.s3_secret_key.get_secret_value(),
            # MinIO is addressed path-style; virtual-host style would need
            # per-bucket DNS.
            config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
            region_name="us-east-1",
        )

    def page_dir(self, page_id: str) -> Path:
        return self._pages_dir / validate_page_id(page_id)

    def stage_inputs(self, page_id: str, file_paths: list[str]) -> None:
        """Bring the declared input *Files* down into the mirror."""
        for file_path in file_paths:
            destination = self._local_path(page_id, file_path)
            destination.parent.mkdir(parents=True, exist_ok=True)

            key = self._layout.key(page_id, file_path)
            try:
                self._client.download_file(self._bucket, key, str(destination))
            except ClientError as error:
                code = error.response.get("Error", {}).get("Code")
                if code in ("404", "NoSuchKey"):
                    raise InputFileMissing(
                        f"The input file {file_path!r} is not in the page {page_id!r}"
                    )
                raise

            logger.debug("Staged %s for page %s", file_path, page_id)

    def snapshot(self, page_id: str) -> dict[str, FileStamp]:
        """How every *File* in the mirror looks right now.

        Taken before a command so that what the *Model* touched can be told
        apart from what was merely staged for it to read.
        """
        page_dir = self.page_dir(page_id)
        if not page_dir.is_dir():
            return {}

        stamps: dict[str, FileStamp] = {}
        for path in page_dir.rglob("*"):
            if path.is_file() and not path.is_symlink():
                stat = path.stat()
                stamps[str(path.relative_to(page_dir))] = (stat.st_size, stat.st_mtime_ns)
        return stamps

    def upload_changes(self, page_id: str, before: dict[str, FileStamp]) -> list[str]:
        """Send back every *File* the *Model* created or changed.

        Deletions do not propagate and a file rewritten byte-for-byte within the
        same clock tick would be missed — see `docs/rough-edges.md`. Neither
        matters for a *Model*, which produces new *Files* rather than removing
        or silently rewriting old ones.
        """
        uploaded: list[str] = []

        for file_path, stamp in self.snapshot(page_id).items():
            if before.get(file_path) == stamp:
                continue

            try:
                source = self._local_path(page_id, file_path)
            except InvalidFilePath:
                # A path the Model made up that would leave its page folder. It
                # is refused rather than repaired: rewriting it would answer a
                # request nobody made and hide whatever produced it.
                logger.error(
                    "The model wrote to a path outside its page and it was not "
                    "uploaded: %r in page %s",
                    file_path,
                    page_id,
                )
                continue

            self._client.upload_file(
                str(source), self._bucket, self._layout.key(page_id, file_path)
            )
            uploaded.append(file_path)

        return uploaded

    def discard(self, page_id: str) -> None:
        """Remove the page's local mirror.

        The mirror is scratch space for one execution, not a cache: leaving it
        behind would grow without bound on a long-lived *Worker*.
        """
        shutil.rmtree(self.page_dir(page_id), ignore_errors=True)

    def _local_path(self, page_id: str, file_path: str) -> Path:
        """Where one *File* sits locally, checked to stay inside its page."""
        return local_path(self._pages_dir, page_id, file_path)
