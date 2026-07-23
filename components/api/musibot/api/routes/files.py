"""The *File* endpoint: presigned URLs for direct transfer to and from MinIO."""

import logging
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, status

from musibot.api.auth import get_owned_page
from musibot.api.config import ApiSettings
from musibot.api.domain import MusicorpusPage
from musibot.api.schemas import FileUrlsRequest, FileUrlsResponse
from musibot.api.storage import StoragePort

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/musicorpus-pages", tags=["files"])


def get_storage(request: Request) -> StoragePort:
    storage: StoragePort | None = request.app.state.storage
    if storage is None:
        # The service is running without object storage configured — the
        # pages-only subset works, but nothing that touches Files does.
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Object storage is not configured",
        )
    return storage


@router.post("/{page_id}/file-urls")
def create_file_urls(
    body: FileUrlsRequest,
    request: Request,
    page: MusicorpusPage = Depends(get_owned_page),
    storage: StoragePort = Depends(get_storage),
) -> FileUrlsResponse:
    """Issue short-lived presigned URLs to `PUT` and/or `GET` *Files* directly
    to and from MinIO, keeping the `api` service out of the byte-path."""
    settings: ApiSettings = request.app.state.settings
    ttl = settings.file_url_ttl_seconds

    response = FileUrlsResponse(
        put={path: storage.presign(page.page_id, path, "put", ttl) for path in body.put},
        get={path: storage.presign(page.page_id, path, "get", ttl) for path in body.get},
        expires_at=datetime.now(UTC) + timedelta(seconds=ttl),
    )
    logger.info(
        "Issued %d put and %d get URLs for page %s",
        len(response.put),
        len(response.get),
        page.page_id,
    )
    return response
