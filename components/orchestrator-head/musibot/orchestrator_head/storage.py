"""Object storage, as a *Pipeline* reaches it: one *File* at a time.

This is the counterpart of the *Worker Head's* storage module and is
deliberately not the same thing. A *Worker Head* mirrors a page's *Files* into a
local directory because its *Model* works with ordinary files and knows nothing
of MinIO. A *Pipeline* is python running inside this process, so it fetches what
it asks for when it asks for it and writes straight back.

That is the simpler arrangement and also the more correct one here. A *Pipeline*
runs for as long as everything it invokes put together, and the *Models* it
invokes write into the same page while it runs — so a local mirror taken at the
start would be stale by the middle, and one refreshed as it went would be a
cache with an invalidation problem. Fetching per use has neither, and moves only
the bytes the *Pipeline* actually cares about.

Every call here is blocking boto3, so callers run them off the event loop.
"""

import logging
from typing import TYPE_CHECKING, Protocol

import boto3
from botocore.client import Config
from botocore.exceptions import ClientError
from musibot.core import S3Settings

if TYPE_CHECKING:
    # Type stubs only. They come from `boto3-stubs[s3]`, which is a *dev*
    # dependency and is therefore absent beside a deployed orchestrator — so
    # importing this at module scope crashes the process on startup, and does
    # it only in production, because every development environment has the
    # stubs installed and nothing local ever notices.
    from mypy_boto3_s3.client import S3Client

logger = logging.getLogger(__name__)


class FileNotInPage(Exception):
    """A *File* a *Pipeline* asked for is not in the page.

    Reported as itself rather than as a boto3 `ClientError`, because the
    ordinary way to get here is a *Pipeline* reading a *File* it expected some
    *Model* to have written — and that message reaches the *User*.
    """


class PageStoragePort(Protocol):
    """What a `PipelineContext` needs of object storage.

    A `Protocol` for two reasons, and the second is the one that matters. It
    lets this component's own tests run without MinIO; and it lets a *Pipeline*
    author unit-test their *Pipeline* against an in-memory page, which is the
    whole of what `musibot.orchestrator_head.testing` provides. So this is part
    of what the component offers, not merely a seam for its own convenience.
    """

    def read(self, page_id: str, file_path: str) -> bytes: ...

    def write(self, page_id: str, file_path: str, data: bytes) -> None: ...

    def list_files(self, page_id: str) -> list[str]: ...

    def exists(self, page_id: str, file_path: str) -> bool: ...


class PageStorage:
    """The bucket holding every *Musicorpus Page*."""

    def __init__(self, settings: S3Settings):
        self._bucket = settings.s3_bucket

        # Where in the bucket this deployment keeps its pages. It must match
        # what the `api` service and every Worker Head were configured with: an
        # Orchestrator rooted differently would read nothing and write where
        # nobody looks, and both halves of that fail quietly.
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

    def read(self, page_id: str, file_path: str) -> bytes:
        """The whole of one *File*, in memory.

        In memory because a *Pipeline* is going to parse or decode it anyway —
        a page scan and a MusicXML file are both things you hold whole — and
        streaming would buy nothing at these sizes.
        """
        try:
            response = self._client.get_object(
                Bucket=self._bucket, Key=self._layout.key(page_id, file_path)
            )
        except ClientError as error:
            code = error.response.get("Error", {}).get("Code")
            if code in ("404", "NoSuchKey"):
                raise FileNotInPage(f"The file {file_path!r} is not in the page {page_id!r}")
            raise

        data: bytes = response["Body"].read()
        logger.debug("Read %s of page %s (%d bytes)", file_path, page_id, len(data))
        return data

    def write(self, page_id: str, file_path: str, data: bytes) -> None:
        """Put one *File* into the page, replacing whatever was there."""
        self._client.put_object(
            Bucket=self._bucket, Key=self._layout.key(page_id, file_path), Body=data
        )
        logger.debug("Wrote %s of page %s (%d bytes)", file_path, page_id, len(data))

    def list_files(self, page_id: str) -> list[str]:
        """Every *File* in the page, as page-relative paths.

        In the storage's own key order, which is lexicographic and therefore
        puts `Staves/10/` before `Staves/2/`. A *Pipeline* wanting staves in
        numeric order sorts them itself — as `docs/signatures.md` says, a set of
        subdivision instances has no order that Musibot could impose.
        """
        prefix = self._layout.prefix(page_id)
        paths: list[str] = []
        paginator = self._client.get_paginator("list_objects_v2")

        for listing in paginator.paginate(Bucket=self._bucket, Prefix=prefix):
            for entry in listing.get("Contents", []):
                key = entry.get("Key")
                # The rooting goes on when a key is built and has to come back
                # off here, or every path would carry the deployment's prefix
                # and none of them would match a *Signature*.
                if key is None or not key.startswith(prefix):
                    continue
                path = key[len(prefix) :]
                if path:
                    paths.append(path)

        return paths

    def exists(self, page_id: str, file_path: str) -> bool:
        """Whether the page holds that *File*."""
        try:
            self._client.head_object(Bucket=self._bucket, Key=self._layout.key(page_id, file_path))
        except ClientError as error:
            code = error.response.get("Error", {}).get("Code")
            if code in ("404", "NoSuchKey", "NoSuchBucket"):
                return False
            raise

        return True
