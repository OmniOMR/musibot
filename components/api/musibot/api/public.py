"""The *General public* tier: throwaway sessions, and the caps on the pool.

The full reasoning is in `docs/public-access.md`; the short version is what the
code here has to get right.

The public gets a bearer token, minted on demand, and it buys nothing —
minting is free and unlimited, so anyone can hold a thousand. It exists only so
that two members of the public do not see each other's *Musicorpus Pages*,
which the ownership check in `auth.py` already does for *Library* users and now
serves both without a second code path.

What actually protects the instance is the pair of **global** caps: how many
*Pipeline Executions* the public may have running at once, and how much of
MinIO public pages may hold between them. Those are what keep a *Library's*
batch run from being starved, and they hold however many public users show up
and however they behave. The **per-session** caps alongside them are courtesy —
they guard against a runaway retry loop or twenty open tabs, and anyone acting
in bad faith steps around them by minting another session. Nothing here
pretends otherwise.

Sessions expire, and that is load-bearing rather than housekeeping: a public
user closes the tab and never deletes anything, so without expiry the storage
pool would fill once and never drain.
"""

import asyncio
import logging
import threading
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException, status
from musibot.core.identifiers import random_id

from musibot.api.config import ApiSettings
from musibot.api.domain import (
    PUBLIC_IDENTITY_PREFIX,
    MusicorpusPageRepository,
    is_public_identity,
)
from musibot.api.executions import ExecutionService
from musibot.api.reclaim import free_page
from musibot.api.storage import StoragePort

logger = logging.getLogger(__name__)

TOKEN_LENGTH = 32
"""Longer than a page ID. A page ID is guessed at through an ownership check
that would reject it anyway; a session token *is* the authentication, so it is
sized to be worth nobody's while."""


@dataclass
class PublicSession:
    """One member of the public, for as long as their session lasts."""

    token: str
    identity: str
    expires_at: datetime

    def is_expired(self, now: datetime) -> bool:
        return now >= self.expires_at


class PublicAccess:
    """The public tier: its sessions, its caps, and the sweep that expires it.

    Constructed whether or not the tier is switched on, so that the wiring has
    no branch in it; when it is off, nothing can be minted and no session ever
    resolves, which is the whole of the difference.
    """

    def __init__(
        self,
        settings: ApiSettings,
        repository: MusicorpusPageRepository,
        *,
        executions: ExecutionService | None = None,
        storage: StoragePort | None = None,
    ):
        self._settings = settings
        self._repository = repository
        self._executions = executions
        self._storage = storage

        # Sessions are read on every public request (from FastAPI's threadpool,
        # since the routes that authenticate are sync) and written by the sweep
        # on the event loop, so this needs the same guarding as the page store.
        self._sessions: dict[str, PublicSession] = {}
        self._lock = threading.Lock()

        # Public bytes as of the last sweep. Starts at zero because the bucket
        # is wiped at startup, so on a fresh service that is the truth.
        self._storage_bytes = 0

    @property
    def enabled(self) -> bool:
        return self._settings.public_access_enabled

    # --- sessions ------------------------------------------------------------

    def mint(self) -> PublicSession:
        """Issue a new *Public Session*.

        Free and unguarded by design — see the module docstring. Raises `404`
        when the tier is switched off, which is the honest answer: a deployment
        without a public tier does not offer this endpoint.
        """
        if not self.enabled:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="This Musibot instance does not offer public access",
            )

        session = PublicSession(
            token=random_id(TOKEN_LENGTH),
            identity=PUBLIC_IDENTITY_PREFIX + random_id(),
            expires_at=datetime.now(UTC)
            + timedelta(seconds=self._settings.public_session_ttl_seconds),
        )
        with self._lock:
            self._sessions[session.token] = session

        logger.info("Minted public session %s until %s", session.identity, session.expires_at)
        return session

    def lookup(self, token: str) -> PublicSession | None:
        """The session a token names, expired or not, or None.

        An expired one is returned rather than hidden so that `auth.py` can say
        *session expired* instead of *unknown token* — the same `401` either
        way, but the Web UI has something truthful to show. It stops resolving
        once the sweep collects it, a minute or so later.

        A plain dict lookup, where a *Library* token gets a constant-time
        comparison: that token is issued by hand and long-lived, while this one
        is 32 random characters that expire within the hour and reach only the
        pages the same session created.
        """
        with self._lock:
            return self._sessions.get(token)

    def is_live(self, identity: str) -> bool:
        """Whether a *Public Session* identity is still good for anything.

        Asked by the [result stream](routes/results.py), which has no page to
        notice the deletion of and would otherwise hold an expired visitor's
        connection open until their browser gave up. A scan rather than an
        index: it is asked once per idle watcher every fifteen seconds, over a
        few hundred sessions at the very most.
        """
        now = datetime.now(UTC)
        with self._lock:
            return any(
                session.identity == identity and not session.is_expired(now)
                for session in self._sessions.values()
            )

    # --- the caps ------------------------------------------------------------

    def check_may_create_page(self, identity: str) -> None:
        """Refuse a public page beyond the caps. A *Library* user is exempt.

        Called before the page exists, so a refusal leaves nothing behind.
        """
        if not is_public_identity(identity):
            return

        # Global first: it is the one that means something, and reporting it
        # first keeps a public user who is over their own page cap from being
        # told to delete a page when that would not help.
        if self._storage_bytes >= self._settings.public_storage_quota_bytes:
            raise HTTPException(
                status_code=status.HTTP_507_INSUFFICIENT_STORAGE,
                detail=(
                    "Public storage is full. Results already produced can still be "
                    "downloaded, but no new page can be created right now."
                ),
            )

        pages = sum(1 for page in self._repository.all_pages() if page.owner == identity)
        if pages >= self._settings.public_max_pages_per_session:
            # No Retry-After: waiting does not help, deleting a page does.
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=(
                    f"A public session may hold {self._settings.public_max_pages_per_session} "
                    "pages at a time. Delete one before creating another."
                ),
            )

    def check_may_start_execution(self, identity: str) -> None:
        """Refuse a public execution beyond the caps. A *Library* user is exempt.

        Both counts are taken from the repository rather than from a counter
        kept alongside it: an execution stops being running for several reasons
        (a result, a timeout, its page deleted) and a tally that missed one
        would leak capacity permanently. Scanning cannot.
        """
        if not is_public_identity(identity):
            return

        # A public execution cannot outlive its timeout, so a slot is certain to
        # free within one. Sooner, usually.
        retry_after = {"Retry-After": str(int(self._settings.public_execution_timeout_seconds))}

        running_by_session = 0
        running_in_public = 0
        for page in self._repository.all_pages():
            if not is_public_identity(page.owner):
                continue
            running = sum(1 for e in page.executions.values() if e.state == "running")
            running_in_public += running
            if page.owner == identity:
                running_by_session += running

        if running_in_public >= self._settings.public_max_concurrent_executions:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="The public demo is busy right now. Try again in a moment.",
                headers=retry_after,
            )

        if running_by_session >= self._settings.public_max_concurrent_executions_per_session:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="This session already has a pipeline execution running.",
                headers=retry_after,
            )

    def execution_timeout(self, identity: str) -> float | None:
        """The deadline a public execution gets, or None to use the general one.

        A ceiling rather than a replacement, so a deployment that lowers the
        general timeout below the public one still gets the lower of the two.
        Together with the global cap this is what bounds public occupancy of
        the *Worker* fleet: `K` workers, for one of these each, at worst.
        """
        if not is_public_identity(identity):
            return None
        return min(
            self._settings.public_execution_timeout_seconds,
            self._settings.pipeline_execution_timeout_seconds,
        )

    # --- the sweep -----------------------------------------------------------

    async def sweep(self) -> None:
        """Expire what is due, then re-measure what the public holds.

        In that order: pages freed now should not be counted in the total the
        next page creation is checked against.
        """
        await self._expire_sessions()
        self._measure_storage()

    async def run_sweeps(self) -> None:
        """Sweep forever, on the interval. Runs as a task for the service's life."""
        while True:
            try:
                await asyncio.sleep(self._settings.public_sweep_interval_seconds)
                await self.sweep()
            except asyncio.CancelledError:
                return
            except Exception:
                # A sweep that raises must not take the loop down with it, or
                # nothing is ever reclaimed again and the tier silently fills.
                logger.exception("Public sweep failed; continuing")

    async def _expire_sessions(self) -> None:
        now = datetime.now(UTC)

        with self._lock:
            expired = {
                session.identity: token
                for token, session in self._sessions.items()
                if session.is_expired(now)
            }

        if not expired:
            return

        # A page whose execution is still running is left for the next sweep
        # rather than deleted underneath it. The public execution timeout is far
        # shorter than the session lifetime, so this defers a page by one sweep
        # at the very worst.
        deferred: set[str] = set()
        for page in self._repository.all_pages():
            if page.owner not in expired:
                continue
            if page.has_running_execution():
                deferred.add(page.owner)
                continue
            await free_page(page, self._repository, self._executions, self._storage)

        collected = {
            identity: token for identity, token in expired.items() if identity not in deferred
        }
        with self._lock:
            for token in collected.values():
                self._sessions.pop(token, None)

        logger.info(
            "Swept %d expired public session(s), %d deferred for a running execution",
            len(collected),
            len(deferred),
        )

    def _measure_storage(self) -> None:
        """Total what public pages hold in MinIO, for the quota to be read against.

        Measured here and cached rather than asked for per request: it is a
        listing of the whole bucket, and page creation must not wait on one.
        The cost is that the quota lags by up to a sweep interval — which is why
        it is set well under the disk's real capacity.
        """
        if self._storage is None:
            return

        public_pages = {
            page.page_id for page in self._repository.all_pages() if is_public_identity(page.owner)
        }
        try:
            sizes = self._storage.page_sizes()
        except Exception:
            # Keep the previous figure rather than falling back to zero: a
            # measurement that fails must not be read as "the pool is empty".
            logger.exception("Could not measure public storage; keeping the last figure")
            return

        self._storage_bytes = sum(
            size for page_id, size in sizes.items() if page_id in public_pages
        )
        logger.info(
            "Public storage holds %.1f MiB of %.1f MiB across %d page(s)",
            self._storage_bytes / 1024**2,
            self._settings.public_storage_quota_bytes / 1024**2,
            len(public_pages),
        )

    # --- for tests -----------------------------------------------------------

    @property
    def storage_bytes(self) -> int:
        """Public bytes as of the last sweep."""
        return self._storage_bytes
