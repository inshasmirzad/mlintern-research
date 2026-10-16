import asyncio
import logging
import os
import sqlite3
import time
import uuid
from pathlib import Path
from typing import Optional, Dict, Any

# Monkeypatch bcrypt >= 4.1.0 to work with passlib
import bcrypt
if not hasattr(bcrypt, "__about__"):
    class _BcryptAbout:
        __version__ = getattr(bcrypt, "__version__", "4.1.0")
    bcrypt.__about__ = _BcryptAbout()

from passlib.context import CryptContext
from jose import jwt, JWTError
from fastapi import HTTPException, status
from pydantic import BaseModel

logger = logging.getLogger(__name__)

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
SECRET_KEY = os.environ.get("JWT_SECRET_KEY", "dev-secret-key-replace-in-production")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 7  # 7 days

class UserCreate(BaseModel):
    username: str
    email: str
    password: str

from database import get_db

# ---------------------------------------------------------------------------
# AuthHandler
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# AuthHandler
# ---------------------------------------------------------------------------

class AuthHandler:
    @property
    def db(self):
        return get_db()

    def initialize(self, db_client: Any) -> None:
        logger.info("AuthHandler: using MongoDB persistence")

    # ------------------------------------------------------------------
    # Password helpers
    # ------------------------------------------------------------------

    def get_password_hash(self, password: str) -> str:
        safe = password.encode("utf-8")[:71].decode("utf-8", "ignore")
        return pwd_context.hash(safe)

    def verify_password(self, plain: str, hashed: str) -> bool:
        safe = plain.encode("utf-8")[:71].decode("utf-8", "ignore")
        return pwd_context.verify(safe, hashed)

    # ------------------------------------------------------------------
    # Token helpers
    # ------------------------------------------------------------------

    def create_access_token(
        self,
        data: dict,
        expires_delta: Optional[float] = None,
    ) -> str:
        to_encode = data.copy()
        expire = time.time() + (
            expires_delta * 60
            if expires_delta
            else ACCESS_TOKEN_EXPIRE_MINUTES * 60
        )
        jti = str(uuid.uuid4())  # unique token ID for revocation
        to_encode.update({"exp": expire, "jti": jti})
        return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

    async def revoke_token(self, token: str) -> bool:
        """Blacklist a JWT by its jti claim. Returns True on success."""
        try:
            payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
            jti = payload.get("jti")
            if not jti:
                return False
            exp = float(payload.get("exp", time.time() + 3600))
            await self.db.revoked_tokens.update_one(
                {"jti": jti},
                {"$setOnInsert": {"jti": jti, "revoked_at": time.time(), "expires_at": exp}},
                upsert=True
            )
            # Background cleanup of already-expired rows (best-effort)
            asyncio.create_task(self.db.revoked_tokens.delete_many({"expires_at": {"$lt": time.time()}}))
            return True
        except JWTError:
            return False

    async def is_token_revoked(self, jti: str) -> bool:
        doc = await self.db.revoked_tokens.find_one({"jti": jti})
        return doc is not None

    # ------------------------------------------------------------------
    # User CRUD
    # ------------------------------------------------------------------

    async def create_user(self, user: UserCreate) -> dict:
        existing = await self.db.users.find_one(
            {"$or": [{"email": user.email}, {"username": user.username}]}
        )
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email or username already registered",
            )

        user_id = f"usr_{int(time.time() * 1000)}"
        user_dict = {
            "user_id": user_id,
            "username": user.username,
            "email": user.email,
            "hashed_password": await asyncio.to_thread(self.get_password_hash, user.password),
            "role": "user",
            "plan": "pro",
            "created_at": time.time(),
        }
        await self.db.users.insert_one(user_dict)
        return {
            "user_id": user_id,
            "username": user.username,
            "email": user.email,
            "role": "user",
            "plan": "pro",
        }

    async def authenticate_user(self, email: str, password: str) -> Optional[dict]:
        user = await self.db.users.find_one({"email": email})
        if not user or not self.verify_password(password, user["hashed_password"]):
            return None
        return user

    # ------------------------------------------------------------------
    # User Interaction History
    # ------------------------------------------------------------------

    async def log_user_interaction(
        self,
        user_id: str,
        session_id: str,
        user_input: str,
        ai_response: str,
        model_used: str,
        token_usage: int = 0
    ) -> None:
        """Log a complete user-agent interaction to the database."""
        doc = {
            "user_id": user_id,
            "session_id": session_id,
            "user_input": user_input,
            "ai_response": ai_response,
            "model_used": model_used,
            "token_usage": token_usage,
            "timestamp": time.time(),
        }
        await self.db.user_interactions.insert_one(doc)

    async def get_user_interactions(self, user_id: str) -> list[dict]:
        """Retrieve interaction history for a user, sorted from newest to oldest."""
        cursor = self.db.user_interactions.find(
            {"user_id": user_id},
            {"_id": 0}  # Exclude MongoDB ObjectId for easy JSON serialization
        ).sort("timestamp", -1)
        return [doc async for doc in cursor]

    async def get_user_from_token(self, token: str) -> Optional[dict]:
        try:
            payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
            user_id: str = payload.get("sub")
            if user_id is None:
                return None

            # Reject revoked tokens
            jti = payload.get("jti")
            if jti and await self.is_token_revoked(jti):
                logger.debug("Rejected revoked token jti=%s", jti)
                return None

            user = await self.db.users.find_one({"user_id": user_id})
            if user:
                return {
                    "user_id": user["user_id"],
                    "username": user["username"],
                    "name": user.get("name", user["username"]),
                    "picture": user.get("picture"),
                    "role": user.get("role", "user"),
                    "plan": user.get("plan", "pro"),
                }

            # Fallback: token is valid but user row is missing (edge case)
            return {
                "user_id": user_id,
                "username": payload.get("username", "user"),
                "role": payload.get("role", "user"),
                "plan": "pro",
            }
        except JWTError:
            return None


auth_handler = AuthHandler()
