"""Anonimowa sesja w ciasteczku: rozdziela dane odwiedzających bez kont.

W bazie trzymamy wyłącznie SHA-256 tokenu. Przełącznik ról nie ma tu znaczenia.
"""

import hashlib
import secrets
from typing import Annotated

from fastapi import Depends, HTTPException, Request, Response, status

from app.settings import Settings, get_settings

COOKIE_NAME = "kops_session"
COOKIE_PATH = "/api"
MAX_TOKEN_LENGTH = 256


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _existing_token(request: Request) -> str | None:
    token = request.cookies.get(COOKIE_NAME)
    if token and len(token) <= MAX_TOKEN_LENGTH:
        return token
    return None


def get_or_create_session(
    request: Request,
    response: Response,
    settings: Annotated[Settings, Depends(get_settings)],
) -> str:
    """Hash tokenu sesji; brak ciasteczka oznacza wydanie nowego (dla POST)."""
    token = _existing_token(request)
    if token is None:
        token = secrets.token_urlsafe(32)
        response.set_cookie(
            COOKIE_NAME,
            token,
            httponly=True,
            samesite="lax",
            path=COOKIE_PATH,
            secure=settings.session_cookie_secure,
        )
    return hash_token(token)


def require_session(request: Request) -> str:
    """Hash tokenu istniejącej sesji; bez ciasteczka 404, bez tworzenia sesji (GET)."""
    token = _existing_token(request)
    if token is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Nie znaleziono odpowiedzi")
    return hash_token(token)


SessionDep = Annotated[str, Depends(get_or_create_session)]
ExistingSessionDep = Annotated[str, Depends(require_session)]
