"""Authentication and page ownership.

A *User* is identified by their bearer token, matched against the map loaded
from configuration. Every page operation is then authorized against ownership:
a *User* may only touch pages they created.
"""

import secrets

from fastapi import Depends, HTTPException, Request, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from musibot.api.domain import MusicorpusPage, MusicorpusPageRepository, PageNotFound

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
) -> str:
    """The *User* making this request, from the `Authorization: Bearer` header.

    Raises `401` if the header is missing, malformed, or names no known token.
    """
    if credentials is None:
        # The scheme reports a missing header and a header that is not a bearer
        # one the same way, and the two are worth telling apart: one means "you
        # sent no token", the other "you sent something that is not one".
        if request.headers.get("Authorization") is None:
            raise _unauthorized("Missing Authorization header")
        raise _unauthorized("Authorization header must be 'Bearer <token>'")

    user = resolve_user(credentials.credentials, request.app.state.api_tokens)
    if user is None:
        raise _unauthorized("Unknown API token")

    return user


def get_owned_page(
    page_id: str,
    request: Request,
    user: str = Depends(current_user),
) -> MusicorpusPage:
    """Fetch a page the current *User* owns.

    A page owned by someone else is reported as `404`, not `403`: a *User* must
    not be able to tell an existing page they cannot see from one that does not
    exist, or page IDs would leak across users.
    """
    repository: MusicorpusPageRepository = request.app.state.pages

    try:
        page = repository.get(page_id)
    except PageNotFound:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No such page")

    if page.owner != user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No such page")

    return page
