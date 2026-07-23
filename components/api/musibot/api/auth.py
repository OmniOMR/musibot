"""Authentication and page ownership.

A *User* is identified by their bearer token, matched against the map loaded
from configuration. Every page operation is then authorized against ownership:
a *User* may only touch pages they created.
"""

import secrets

from fastapi import Depends, Header, HTTPException, Request, status

from musibot.api.domain import MusicorpusPage, MusicorpusPageRepository, PageNotFound


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
    authorization: str | None = Header(default=None),
) -> str:
    """The *User* making this request, from the `Authorization: Bearer` header.

    Raises `401` if the header is missing, malformed, or names no known token.
    """
    if authorization is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Authorization header",
            headers={"WWW-Authenticate": "Bearer"},
        )

    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authorization header must be 'Bearer <token>'",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user = resolve_user(token, request.app.state.api_tokens)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unknown API token",
            headers={"WWW-Authenticate": "Bearer"},
        )

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
