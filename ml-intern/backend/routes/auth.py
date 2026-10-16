"""Authentication routes for HF OAuth.

Handles the OAuth 2.0 authorization code flow with HF as provider.
After successful auth, sets an HttpOnly cookie with the access token.
"""

import logging
import os
import secrets
import time
from urllib.parse import urlencode

import httpx
from dependencies import (
    AUTH_ENABLED,
    get_current_user,
)
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel

router = APIRouter(prefix="/auth", tags=["auth"])
logger = logging.getLogger(__name__)

class RegisterRequest(BaseModel):
    username: str
    email: str
    password: str

class LoginRequest(BaseModel):
    email: str
    password: str

@router.post("/register")
async def register_user(req: RegisterRequest):
    from auth_local import auth_handler, UserCreate
    try:
        user = await auth_handler.create_user(UserCreate(**req.model_dump()))
        return {"status": "ok", "user": user}
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/login")
async def login_user(req: LoginRequest):
    from auth_local import auth_handler
    user = await auth_handler.authenticate_user(req.email, req.password)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    token = auth_handler.create_access_token(
        {"sub": user["user_id"], "username": user["username"], "role": user.get("role", "user")}
    )
    return {
        "access_token": token,
        "token_type": "bearer",
        "user": {"username": user["username"], "user_id": user["user_id"]},
    }


@router.post("/logout")
async def logout_user(request: Request):
    """Revoke the current local JWT so it cannot be reused."""
    from auth_local import auth_handler
    from dependencies import bearer_token_from_header

    token = bearer_token_from_header(request.headers.get("Authorization", ""))
    if token:
        await auth_handler.revoke_token(token)
    return {"status": "logged_out"}




@router.get("/status")
async def auth_status() -> dict:
    """Check if OAuth is enabled on this instance."""
    return {"auth_enabled": AUTH_ENABLED}


@router.get("/me")
async def get_me(user: dict = Depends(get_current_user)) -> dict:
    """Get current user info. Returns the authenticated user or dev user.

    Uses the shared auth dependency which handles cookie + Bearer token.
    """
    return {key: value for key, value in user.items() if not key.startswith("_")}

@router.get("/history")
async def get_history(user: dict = Depends(get_current_user)) -> list[dict]:
    """Retrieve the complete chat history for the current user."""
    from auth_local import auth_handler
    user_id = user.get("user_id") or user.get("username")
    if not user_id:
        raise HTTPException(status_code=401, detail="User ID not found in token")
    return await auth_handler.get_user_interactions(user_id)
