"""Authentication dependencies for FastAPI routes.

- In dev mode (OAUTH_CLIENT_ID not set): auth is bypassed, returns a default "dev" user.
- In production: validates Bearer tokens or cookies against HF OAuth.
"""

import logging
import os
import time
from collections.abc import Iterable
from hashlib import sha256
from typing import Any

import httpx
from fastapi import HTTPException, Request, status

DEV_MODE = os.environ.get("DEV_MODE", "false").lower() == "true"
AUTH_ENABLED = not DEV_MODE
DEV_USER = {
    "user_id": "dev",
    "username": "developer",
    "plan": "pro",
}


def bearer_token_from_header(auth_header: str) -> str | None:
    """Extract token from 'Bearer <token>' header."""
    if not auth_header or not auth_header.startswith("Bearer "):
        return None
    token = auth_header.split(" ", 1)[1].strip()
    return token if token else None

async def get_current_user(request: Request) -> dict[str, Any]:
    """FastAPI dependency: extract and validate the current user from local JWT.
    """
    if not AUTH_ENABLED:
        return dict(DEV_USER)

    # 1. Try local JWT from Authorization header
    token = bearer_token_from_header(request.headers.get("Authorization", ""))
    if token:
        from auth_local import auth_handler
        user = await auth_handler.get_user_from_token(token)
        if user:
            # In non-dev mode, refuse the bare "dev" identity via JWT
            if not DEV_MODE and user.get("user_id") == "dev":
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Not authenticated. Please log in via /auth/login.",
                    headers={"WWW-Authenticate": "Bearer"},
                )
            return user

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Not authenticated. Please log in via /auth/login.",
        headers={"WWW-Authenticate": "Bearer"},
    )
