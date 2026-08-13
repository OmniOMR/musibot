"""The *General public* tier: sessions, the caps on the pool, and the sweep.

The distinction these tests are built around is the one the design turns on:
the **global** caps are the defence and must hold against someone minting all
the sessions they like, while the **per-session** caps are courtesy and are
expected to be bypassable exactly that way. See `docs/public-access.md`.
"""

import asyncio
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from musibot.api.discovery import ProviderRegistry
from musibot.api.domain import MusicorpusPageRepository
from tests.conftest import ClientBuilder, public_access_of
from tests.fakes import FakePublisher, FakeStorage
from tests.test_discovery import orchestrator_announcement

PIPELINE = "hello-world"
VERSION = "1.0.0"


@pytest.fixture
def public(build_client: ClientBuilder) -> Iterator[TestClient]:
    """An instance with the public tier on and its default, roomy caps."""
    with build_client(public_access_enabled=True) as client:
        yield client


@pytest.fixture(autouse=True)
def announce_pipeline(registry: ProviderRegistry) -> None:
    """Make `hello-world` runnable — a *Pipeline* nobody announces is a `404`."""
    registry.record(orchestrator_announcement())


def session(client: TestClient) -> dict[str, str]:
    """Mint a session and return the headers that authenticate as it."""
    response = client.post("/public-sessions")
    assert response.status_code == 201, response.text
    return {"Authorization": f"Bearer {response.json()['token']}"}


def new_page(client: TestClient, headers: dict[str, str]) -> str:
    response = client.post("/musicorpus-pages", headers=headers)
    assert response.status_code == 201, response.text
    page_id: str = response.json()["page_id"]
    return page_id


def start_execution(client: TestClient, page_id: str, headers: dict[str, str]) -> Any:
    return client.post(
        f"/musicorpus-pages/{page_id}/pipeline-executions",
        headers=headers,
        json={"pipeline_name": PIPELINE, "pipeline_version": VERSION, "input": ["image.jpg"]},
    )


def sweep(client: TestClient) -> None:
    """Run one sweep by hand, instead of waiting out the interval."""
    asyncio.run(public_access_of(client).sweep())


def identity_of(client: TestClient, headers: dict[str, str]) -> str:
    """The owner string a session's pages carry."""
    found = public_access_of(client).lookup(headers["Authorization"].removeprefix("Bearer "))
    assert found is not None
    return found.identity


# --- minting -----------------------------------------------------------------


def test_public_access_can_be_switched_off(build_client: ClientBuilder) -> None:
    """A Libraries-only deployment says so, in one line of its configuration.

    It is on by default because the Web UI cannot do anything without it: every
    visitor arrives holding no token, so an instance started without this would
    answer `404` to the first thing the app does.
    """
    with build_client(public_access_enabled=False) as client:
        assert client.post("/public-sessions").status_code == 404


def test_a_minted_session_authenticates(public: TestClient) -> None:
    response = public.post("/public-sessions")

    assert response.status_code == 201
    body = response.json()
    assert body["token"]
    assert body["expires_at"]

    headers = {"Authorization": f"Bearer {body['token']}"}
    assert public.post("/musicorpus-pages", headers=headers).status_code == 201


def test_every_session_gets_a_distinct_token(public: TestClient) -> None:
    tokens = {public.post("/public-sessions").json()["token"] for _ in range(20)}

    assert len(tokens) == 20


def test_the_public_cannot_see_each_others_pages(public: TestClient) -> None:
    """The one thing the token is actually for."""
    mine, yours = session(public), session(public)
    page_id = new_page(public, mine)

    assert public.get(f"/musicorpus-pages/{page_id}", headers=mine).status_code == 200
    # A 404 rather than a 403: an existing page must not be distinguishable
    # from one that never existed.
    assert public.get(f"/musicorpus-pages/{page_id}", headers=yours).status_code == 404


def test_a_public_session_cannot_touch_a_library_users_page(
    public: TestClient, alice: dict[str, str]
) -> None:
    page_id = new_page(public, alice)

    assert public.get(f"/musicorpus-pages/{page_id}", headers=session(public)).status_code == 404


# --- per-session caps: courtesy ----------------------------------------------


def test_a_session_may_hold_only_so_many_pages(build_client: ClientBuilder) -> None:
    with build_client(public_access_enabled=True, public_max_pages_per_session=2) as client:
        headers = session(client)
        new_page(client, headers)
        new_page(client, headers)

        response = client.post("/musicorpus-pages", headers=headers)

        assert response.status_code == 429
        # No Retry-After: waiting does not help, deleting a page does.
        assert "Retry-After" not in response.headers


def test_deleting_a_page_makes_room_again(build_client: ClientBuilder) -> None:
    with build_client(public_access_enabled=True, public_max_pages_per_session=1) as client:
        headers = session(client)
        page_id = new_page(client, headers)
        assert client.post("/musicorpus-pages", headers=headers).status_code == 429

        client.delete(f"/musicorpus-pages/{page_id}", headers=headers)

        assert client.post("/musicorpus-pages", headers=headers).status_code == 201


def test_a_session_runs_one_execution_at_a_time(build_client: ClientBuilder) -> None:
    with build_client(
        public_access_enabled=True,
        public_max_concurrent_executions=10,
        public_max_concurrent_executions_per_session=1,
    ) as client:
        headers = session(client)
        assert start_execution(client, new_page(client, headers), headers).status_code == 201

        response = start_execution(client, new_page(client, headers), headers)

        assert response.status_code == 429
        assert response.headers["Retry-After"]


def test_the_per_session_caps_are_bypassed_by_minting_another_session(
    build_client: ClientBuilder,
) -> None:
    """Deliberately true, and documented as such.

    The per-session caps guard against a runaway retry loop, not against
    someone determined; the global caps below are what actually hold.
    """
    with build_client(
        public_access_enabled=True,
        public_max_pages_per_session=1,
        public_max_concurrent_executions=10,
        public_max_concurrent_executions_per_session=1,
    ) as client:
        first = session(client)
        start_execution(client, new_page(client, first), first)

        second = session(client)

        assert start_execution(client, new_page(client, second), second).status_code == 201


# --- global caps: the defence ------------------------------------------------


def test_the_public_tier_runs_only_so_many_executions_at_once(
    build_client: ClientBuilder,
) -> None:
    """The cap that keeps a Library's batch run from being starved.

    Each execution is started from its own freshly minted session, which is
    exactly how the per-session cap is escaped — and the global one still holds.
    """
    with build_client(public_access_enabled=True, public_max_concurrent_executions=2) as client:
        for _ in range(2):
            headers = session(client)
            assert start_execution(client, new_page(client, headers), headers).status_code == 201

        headers = session(client)
        response = start_execution(client, new_page(client, headers), headers)

        assert response.status_code == 429
        assert response.headers["Retry-After"]
        assert "busy" in response.json()["detail"]


def test_a_settled_execution_frees_a_public_slot(
    build_client: ClientBuilder, repository: MusicorpusPageRepository
) -> None:
    with build_client(public_access_enabled=True, public_max_concurrent_executions=1) as client:
        first = session(client)
        page_id = new_page(client, first)
        start_execution(client, page_id, first)

        second = session(client)
        assert start_execution(client, new_page(client, second), second).status_code == 429

        # The execution settles, as a result off RabbitMQ would settle it.
        repository.get(page_id).executions[1].state = "completed"

        assert start_execution(client, new_page(client, second), second).status_code == 201


def test_a_library_user_is_exempt_from_the_public_caps(
    build_client: ClientBuilder, alice: dict[str, str]
) -> None:
    """The whole point: the public tier fills up and the Libraries carry on."""
    with build_client(
        public_access_enabled=True,
        public_max_concurrent_executions=1,
        public_max_pages_per_session=1,
    ) as client:
        public_headers = session(client)
        start_execution(client, new_page(client, public_headers), public_headers)

        # The public tier is now full. Alice is unaffected, in both dimensions.
        for _ in range(3):
            assert start_execution(client, new_page(client, alice), alice).status_code == 201


def test_public_storage_quota_refuses_new_pages(
    build_client: ClientBuilder, storage: FakeStorage
) -> None:
    with build_client(public_access_enabled=True, public_storage_quota_bytes=1000) as client:
        headers = session(client)
        page_id = new_page(client, headers)

        # Stand in for bytes uploaded straight to MinIO, which this service
        # never sees — it only learns of them at the next sweep. Until then the
        # quota is over and page creation still succeeds, which is the lag the
        # design accepts and `docs/rough-edges.md` records.
        storage.put(page_id, "image.jpg", 5000)
        assert client.post("/musicorpus-pages", headers=headers).status_code == 201

        sweep(client)

        assert client.post("/musicorpus-pages", headers=headers).status_code == 507
        assert public_access_of(client).storage_bytes == 5000


def test_a_library_users_bytes_are_not_charged_to_the_public_quota(
    build_client: ClientBuilder, storage: FakeStorage, alice: dict[str, str]
) -> None:
    with build_client(public_access_enabled=True, public_storage_quota_bytes=1000) as client:
        storage.put(new_page(client, alice), "image.jpg", 999_999)

        sweep(client)

        assert public_access_of(client).storage_bytes == 0
        assert client.post("/musicorpus-pages", headers=session(client)).status_code == 201


# --- session lifetime and the sweep ------------------------------------------


def test_an_expired_session_is_told_so(build_client: ClientBuilder) -> None:
    with build_client(public_access_enabled=True, public_session_ttl_seconds=0.0) as client:
        headers = session(client)

        response = client.post("/musicorpus-pages", headers=headers)

        assert response.status_code == 401
        # A nicety while the session is expired but not yet swept — below, once
        # it is collected, the very same token reads as unknown. The `401` is
        # the contract; this message is not.
        assert response.json()["detail"] == "Public session expired"


def test_the_sweep_frees_the_pages_of_an_expired_session(
    build_client: ClientBuilder, storage: FakeStorage, repository: MusicorpusPageRepository
) -> None:
    """Why expiry is load-bearing: nobody deletes their own pages."""
    with build_client(public_access_enabled=True, public_session_ttl_seconds=0.0) as client:
        # The page is created through the repository rather than the endpoint,
        # because the session is already expired and the endpoint would refuse.
        headers = session(client)
        page_id = repository.create(owner=identity_of(client, headers)).page_id

        sweep(client)

        assert storage.deleted_pages == [page_id]
        assert repository.count() == 0
        # The session goes with its pages: the token no longer resolves at all.
        assert client.post("/musicorpus-pages", headers=headers).json()["detail"] == (
            "Unknown API token"
        )


def test_the_sweep_leaves_a_page_whose_execution_is_still_running(
    build_client: ClientBuilder, repository: MusicorpusPageRepository
) -> None:
    with build_client(public_access_enabled=True, public_session_ttl_seconds=0.0) as client:
        page = repository.create(owner=identity_of(client, session(client)))
        page.add_execution(PIPELINE, VERSION, ["image.jpg"], {})

        sweep(client)

        assert repository.count() == 1

        # Once it settles, the next sweep takes it.
        page.executions[1].state = "completed"
        sweep(client)

        assert repository.count() == 0


def test_a_library_users_pages_are_never_swept(
    build_client: ClientBuilder, repository: MusicorpusPageRepository, alice: dict[str, str]
) -> None:
    with build_client(public_access_enabled=True, public_session_ttl_seconds=0.0) as client:
        new_page(client, alice)
        session(client)

        sweep(client)

        assert repository.count() == 1


# --- the shorter public deadline ---------------------------------------------


def test_a_public_execution_gets_the_shorter_timeout(
    build_client: ClientBuilder, publisher: FakePublisher, alice: dict[str, str]
) -> None:
    """Half of the guarantee to the Libraries: K workers, one deadline each."""
    with build_client(
        public_access_enabled=True,
        public_execution_timeout_seconds=7.0,
        pipeline_execution_timeout_seconds=300.0,
    ) as client:
        headers = session(client)
        start_execution(client, new_page(client, headers), headers)
        public_message = publisher.published[-1]

        start_execution(client, new_page(client, alice), alice)
        library_message = publisher.published[-1]

        assert public_message.expiration_seconds == 7.0
        assert library_message.expiration_seconds == 300.0


def test_the_public_timeout_is_a_ceiling_not_a_replacement(
    build_client: ClientBuilder, publisher: FakePublisher
) -> None:
    """A deployment whose general timeout is already lower keeps the lower one."""
    with build_client(
        public_access_enabled=True,
        public_execution_timeout_seconds=60.0,
        pipeline_execution_timeout_seconds=5.0,
    ) as client:
        headers = session(client)
        start_execution(client, new_page(client, headers), headers)

        assert publisher.published[-1].expiration_seconds == 5.0
