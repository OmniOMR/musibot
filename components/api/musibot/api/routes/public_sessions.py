"""The *Public Session* endpoint: how the *General public* gets a token.

The one endpoint of this service that requires no authentication, since it is
what authentication is obtained from. That is safe only because the token it
hands out buys nothing — see `public.py` and `docs/public-access.md`.
"""

import logging

from fastapi import APIRouter, Request, status

from musibot.api.public import PublicAccess
from musibot.api.schemas import PublicSessionView

logger = logging.getLogger(__name__)

router = APIRouter(tags=["public-access"])


@router.post("/public-sessions", status_code=status.HTTP_201_CREATED)
def create_public_session(request: Request) -> PublicSessionView:
    """Mint a *Public Session* for a member of the *General public*.

    Answers `404` on an instance that does not offer public access.
    """
    public: PublicAccess = request.app.state.public_access
    session = public.mint()
    return PublicSessionView(token=session.token, expires_at=session.expires_at)
