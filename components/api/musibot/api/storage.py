"""Object storage: the `api` service's view of MinIO.

The service is never in the file byte-path — *Users* upload and download *Files*
straight to and from MinIO through presigned URLs. So this module does only
three things: hand out those presigned URLs, delete a page's folder when the
page is deleted, and wipe the bucket clean at startup.

Presigned URLs are signed against the *public* MinIO address (`s3_public_url`),
which is where a *User* redeems them, while the service's own operations use the
internal address (`s3_endpoint_url`). In development the two are the same.
"""

import logging
from typing import Literal, Protocol

import boto3
from botocore.client import Config
from musibot.core import S3Settings, object_key, object_prefix
from mypy_boto3_s3.client import S3Client

logger = logging.getLogger(__name__)

HttpMethod = Literal["get", "put"]


class StoragePort(Protocol):
    """What the rest of the service needs from object storage.

    A `Protocol` so a test can supply a fake without boto3 or a live MinIO, and
    so the routes never import the concrete client.
    """

    def presign(
        self, page_id: str, file_path: str, method: HttpMethod, ttl_seconds: float
    ) -> str: ...

    def delete_page(self, page_id: str) -> None: ...

    def wipe_bucket(self) -> None: ...


def _make_client(endpoint_url: str, settings: S3Settings) -> S3Client:
    return boto3.client(
        "s3",
        endpoint_url=endpoint_url,
        aws_access_key_id=settings.s3_access_key,
        aws_secret_access_key=settings.s3_secret_key.get_secret_value(),
        # MinIO is addressed path-style (bucket in the path, not the hostname);
        # virtual-host style would need per-bucket DNS.
        config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
        region_name="us-east-1",
    )


class Storage:
    """The MinIO bucket that holds every *Musicorpus Page*."""

    def __init__(self, settings: S3Settings):
        self._bucket = settings.s3_bucket

        # One client for the service's own calls, over the internal endpoint.
        self._client = _make_client(settings.s3_endpoint_url, settings)

        # A second client whose endpoint is the public address, used only to
        # build presigned URLs. Presigning is a local computation — it makes no
        # network call — so this client never has to reach that address itself;
        # it only has to sign a request for the host the User will send it to.
        public_url = settings.s3_public_url or settings.s3_endpoint_url
        self._signing_client = _make_client(public_url, settings)

    def presign(self, page_id: str, file_path: str, method: HttpMethod, ttl_seconds: float) -> str:
        """A short-lived URL to `PUT` or `GET` one *File* directly to/from MinIO."""
        operation = "get_object" if method == "get" else "put_object"
        return self._signing_client.generate_presigned_url(
            operation,
            Params={"Bucket": self._bucket, "Key": object_key(page_id, file_path)},
            ExpiresIn=int(ttl_seconds),
        )

    def delete_page(self, page_id: str) -> None:
        """Remove everything stored under a page's folder.

        Best-effort: a still-running *Worker* may write more into the folder
        after this returns, which the next startup wipe will clear. See
        `docs/rough-edges.md`.
        """
        self._delete_prefix(object_prefix(page_id))

    def wipe_bucket(self) -> None:
        """Empty the whole bucket. Run once at service startup.

        The service's state is ephemeral and rebuilt empty on every start, so
        any objects MinIO still holds are stale — from a previous run that
        crashed before cleaning up — and must not be mistaken for a live page's
        *Files*.
        """
        logger.info("Wiping the MinIO bucket %r clean at startup", self._bucket)
        self._delete_prefix("")

    def _delete_prefix(self, prefix: str) -> None:
        paginator = self._client.get_paginator("list_objects_v2")
        batch: list[str] = []

        for page in paginator.paginate(Bucket=self._bucket, Prefix=prefix):
            for entry in page.get("Contents", []):
                key = entry.get("Key")
                if key is None:
                    continue
                batch.append(key)
                # S3 delete_objects takes at most 1000 keys per call.
                if len(batch) == 1000:
                    self._delete_batch(batch)
                    batch = []

        if batch:
            self._delete_batch(batch)

    def _delete_batch(self, keys: list[str]) -> None:
        self._client.delete_objects(
            Bucket=self._bucket,
            Delete={"Objects": [{"Key": key} for key in keys], "Quiet": True},
        )
