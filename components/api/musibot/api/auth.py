"""Authentication and page ownership.

A *User* is identified by their bearer token, matched against the map loaded
from configuration. A member of the *General public* is identified the same
way, by a token naming a *Public Session* they minted a moment ago (see
`public.py`). The two arrive over the same header and resolve to the same kind
of thing — an identity string — which is what lets everything downstream, the
ownership check included, treat them alike.

Every page operation is then authorized against ownership: a caller may only
touch pages they created.
"""

import secrets
from dataclasses import dataclass
from datetime import UTC, datetime

from fastapi import Depends, HTTPException, Request, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from musibot.api.domain import MusicorpusPage, MusicorpusPageRepository, PageNotFound
from musibot.api.public import PublicAccess

bearer_scheme = HTTPBearer(
    scheme_name="API token",
    description="The API token issued to you, sent as `Authorization: Bearer <token>`.",
    # This service answers a missing or malformed token itself, below, so that
    # the three ways of getting it wrong are told apart in the response body.
    auto_error=False,
)
"""How a *User* authenticates.

Declared as a security scheme rather than read as a plain header, so that it
appears once in the OpenAPI document under `securitySchemes` and the interactive
docs offer the **Authorize** button. Spelling it as a header parameter made it a
per-endpoint field that had to be retyped for every request.
"""


@dataclass(frozen=True)
class Caller:
    """Who is making a request, once their token has been resolved.

    `identity` is what a page's `owner` is compared against, and is all the
    ownership check needs. `is_public` is what the caps in `public.py` key off —
    a flag rather than a prefix test at each call site, so that "is this the
    public tier" is asked in one place and answered the same way everywhere.
    """

    identity: str
    is_public: bool


def _unauthorized(detail: str) -> HTTPException:
    """A `401` that says how to authenticate, as the status code requires."""
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


def resolve_user(token: str, tokens: dict[str, str]) -> str | None:
    """Return the user a token identifies, or None.

    The comparison is constant-time against every known token, so that a
    response cannot be timed to learn how much of a guessed token was right.
    """
    matched: str | None = None
    for known_token, user in tokens.items():
        if secrets.compare_digest(token, known_token):
            matched = user
    return matched


def current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Security(bearer_scheme),
) -> Caller:
    """Who is making this request, from the `Authorization: Bearer` header.

    Configured *Library* tokens are tried first: they are the users this service
    exists for, and a public session can never collide with one, since public
    identities carry a prefix `config.py` refuses to load.

    Raises `401` if the header is missing, malformed, or names no live token.
    """
    if credentials is None:
        # The scheme reports a missing header and a header that is not a bearer
        # one the same way, and the two are worth telling apart: one means "you
        # sent no token", the other "you sent something that is not one".
        if request.headers.get("Authorization") is None:
            raise _unauthorized("Missing Authorization header")
        raise _unauthorized("Authorization header must be 'Bearer <token>'")

    token = credentials.credentials

    user = resolve_user(token, request.app.state.api_tokens)
    if user is not None:
        return Caller(identity=user, is_public=False)

    public: PublicAccess = request.app.state.public_access
    session = public.lookup(token)
    if session is not None:
        if session.is_expired(datetime.now(UTC)):
            # A nicety, not a contract: it holds only until the sweep collects
            # the session, after which the token is simply unknown. A client
            # must not branch on this message — the status is `401` either way,
            # and what tells the Web UI to say "session expired, please reload"
            # is that it was holding a public session at all.
            raise _unauthorized("Public session expired")
        return Caller(identity=session.identity, is_public=True)

    raise _unauthorized("Unknown API token")


def get_owned_page(
    page_id: str,
    request: Request,
    caller: Caller = Depends(current_user),
) -> MusicorpusPage:
    """Fetch a page the current caller owns.

    A page owned by someone else is reported as `404`, not `403`: a caller must
    not be able to tell an existing page they cannot see from one that does not
    exist, or page IDs would leak across users. This is also the whole of what
    keeps two members of the public apart, since a *Public Session* is an owner
    like any other.
    """
    repository: MusicorpusPageRepository = request.app.state.pages

    try:
        page = repository.get(page_id)
    except PageNotFound:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No such page")

    if page.owner != caller.identity:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No such page")

    return page
