"""The *File* endpoint: presigned URLs for direct transfer to and from MinIO."""

import logging
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, status

from musibot.api.auth import get_owned_page
from musibot.api.config import ApiSettings
from musibot.api.domain import MusicorpusPage
from musibot.api.schemas import FileListingResponse, FileUrlsRequest, FileUrlsResponse
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


@router.get("/{page_id}/files")
def list_files(
    page: MusicorpusPage = Depends(get_owned_page),
    storage: StoragePort = Depends(get_storage),
) -> FileListingResponse:
    """List the *Files* a *MusicorpusPage* currently holds.

    A *User* knows what they uploaded but not what a *Pipeline* produced —
    a page-level run writes a `Staves/{n}/` folder whose size depends on the
    page — so this is how the outputs are discovered before URLs are asked for.

    It is also how progress is watched: poll it while an execution runs and
    *Files* appear as they are written. Polling is the whole of the mechanism
    for now; the SSE stream that will replace it (see `docs/http-api.md`) is not
    implemented, and until it is, a caller sees a finished execution's outputs
    arrive together rather than one at a time.

    Answered from storage rather than from anything remembered, so it stays
    true across a *File* that a later execution overwrote.
    """
    files = storage.list_page_files(page.page_id)
    logger.info("Listed %d files of page %s", len(files), page.page_id)
    return FileListingResponse.of(files)


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
