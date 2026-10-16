import asyncio
import logging
import os
import time
import threading
from typing import Dict, List, Optional, TYPE_CHECKING, Any
from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from motor.motor_asyncio import AsyncIOMotorClient

logger = logging.getLogger(__name__)


class TokenInfo(BaseModel):
    id: str
    provider: str
    key: str
    is_active: bool = True
    cooldown_until: float = 0.0
    error_count: int = 0
    added_at: float = Field(default_factory=time.time)


class TokenPool:
    def __init__(self):
        self.tokens: Dict[str, List[TokenInfo]] = {}
        self.lock = threading.Lock()
        self.db = None

    async def initialize(self, db_client: Any = None):
        """Load tokens from environment variables (and optionally the database)."""
        if db_client:
            self.db = db_client.ml_intern

        # ----------------------------------------------------------------
        # B1 FIX: All keys come from environment variables only.
        # No keys are hardcoded in source.
        #
        # Supported env vars:
        #   GEMINI_API_KEY / GOOGLE_API_KEY
        #   MISTRAL_API_KEY, MISTRAL_API_KEY_1, MISTRAL_API_KEY_2, MISTRAL_API_KEY_3
        #   OPENAI_API_KEY
        #   HF_TOKEN / HUGGING_FACE_HUB_TOKEN
        # ----------------------------------------------------------------
        new_tokens: Dict[str, List[TokenInfo]] = {}

        def _add(provider: str, key: str | None, token_id: str) -> None:
            if not key or not key.strip():
                return
            key = key.strip()
            if provider not in new_tokens:
                new_tokens[provider] = []
            # Avoid duplicates
            if any(t.key == key for t in new_tokens[provider]):
                return
            new_tokens[provider].append(TokenInfo(id=token_id, provider=provider, key=key))

        # Gemini
        _add("gemini", os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY"), "env_gemini")

        # Mistral — primary + up to 3 extra keys
        _add("mistral", os.environ.get("MISTRAL_API_KEY"), "env_mistral")
        _add("mistral", os.environ.get("MISTRAL_API_KEY_1"), "env_mistral_1")
        _add("mistral", os.environ.get("MISTRAL_API_KEY_2"), "env_mistral_2")
        _add("mistral", os.environ.get("MISTRAL_API_KEY_3"), "env_mistral_3")

        # OpenAI
        _add("openai", os.environ.get("OPENAI_API_KEY"), "env_openai")

        # HuggingFace
        _add(
            "huggingface",
            os.environ.get("HF_TOKEN") or os.environ.get("HUGGING_FACE_HUB_TOKEN"),
            "env_huggingface",
        )

        # Load additional tokens from SQLite database
        if self.db is not None:
            try:
                import sqlite3
                conn = sqlite3.connect('users.db')
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                
                # Check if api_tokens table exists
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='api_tokens'")
                if cursor.fetchone():
                    cursor.execute("SELECT * FROM api_tokens WHERE is_active = 1")
                    db_tokens = cursor.fetchall()
                    for t in db_tokens:
                        provider = t["provider"]
                        if provider not in new_tokens:
                            new_tokens[provider] = []
                        # Skip duplicates already loaded from env
                        if not any(existing.key == t["key"] for existing in new_tokens[provider]):
                            new_tokens[provider].append(TokenInfo(
                                id=t["id"],
                                provider=provider,
                                key=t["key"],
                                is_active=bool(t["is_active"]),
                                cooldown_until=t["cooldown_until"],
                                error_count=t["error_count"],
                                added_at=t["added_at"]
                            ))
                conn.close()
            except Exception as e:
                logger.warning("Failed to load tokens from SQLite DB: %s", e)

        with self.lock:
            self.tokens = new_tokens

        total = sum(len(v) for v in new_tokens.values())
        logger.info(
            "TokenPool initialized: %d token(s) across providers: %s",
            total,
            list(new_tokens.keys()),
        )

    # ------------------------------------------------------------------
    # Token selection
    # ------------------------------------------------------------------

    def get_token(self, provider: str) -> Optional[str]:
        """Get the next available token for a provider (round-robin)."""
        with self.lock:
            if provider not in self.tokens or not self.tokens[provider]:
                return None

            now = time.time()
            available = [
                t for t in self.tokens[provider] if t.is_active and t.cooldown_until < now
            ]
            if not available:
                logger.warning("No available tokens for provider: %s", provider)
                return None

            # Round-robin: pick first available, rotate to end
            token = available[0]
            self.tokens[provider].remove(token)
            self.tokens[provider].append(token)
            return token.key

    def get_best_available_token(self) -> tuple[Optional[str], Optional[str]]:
        """Get the first available token, checking providers in preferred order."""
        preferred_order = ["mistral", "gemini", "openai", "huggingface"]
        with self.lock:
            providers: list[str] = []
            for p in preferred_order:
                if p in self.tokens:
                    providers.append(p)
            for p in self.tokens:
                if p not in preferred_order:
                    providers.append(p)

            now = time.time()
            for provider in providers:
                available = [
                    t for t in self.tokens[provider] if t.is_active and t.cooldown_until < now
                ]
                if available:
                    token = available[0]
                    self.tokens[provider].remove(token)
                    self.tokens[provider].append(token)
                    return provider, token.key
        return None, None

    # ------------------------------------------------------------------
    # Error reporting
    # ------------------------------------------------------------------

    def report_error(self, provider: str, key: str, is_rate_limit: bool = False) -> None:
        """Report an error for a specific key to trigger cooldown."""
        with self.lock:
            if provider not in self.tokens:
                return
            for t in self.tokens[provider]:
                if t.key == key:
                    t.error_count += 1
                    if is_rate_limit:
                        t.cooldown_until = time.time() + 60.0  # 1-minute cooldown on 429
                        logger.warning(
                            "Rate limit hit for provider=%s. 60s cooldown applied.", provider
                        )
                    else:
                        # Auth/other errors: longer cooldown to avoid tight retry loops
                        t.cooldown_until = time.time() + 30.0
                        logger.warning(
                            "Auth/error for provider=%s. 30s cooldown applied.", provider
                        )
                    break

    def report_error_by_key(self, key: str, is_rate_limit: bool = False) -> None:
        """Report an error by API key value alone (provider auto-detected)."""
        with self.lock:
            for provider, token_list in self.tokens.items():
                for t in token_list:
                    if t.key == key:
                        t.error_count += 1
                        cooldown = 60.0 if is_rate_limit else 30.0
                        t.cooldown_until = time.time() + cooldown
                        logger.warning(
                            "Cooldown %.0fs applied to key in provider=%s (rate_limit=%s)",
                            cooldown,
                            provider,
                            is_rate_limit,
                        )
                        return

    # ------------------------------------------------------------------
    # Admin CRUD
    # ------------------------------------------------------------------

    async def add_token(self, provider: str, key: str) -> str:
        """Add a new token to the pool and persist to DB if available."""
        token_id = f"db_{int(time.time() * 1000)}"
        token = TokenInfo(id=token_id, provider=provider, key=key)
        with self.lock:
            if provider not in self.tokens:
                self.tokens[provider] = []
            self.tokens[provider].append(token)
        if self.db is not None:
            await self.db.api_tokens.insert_one(token.model_dump())
        return token_id

    def get_all_tokens(self) -> List[dict]:
        """List all tokens with keys masked for safe display."""
        with self.lock:
            result = []
            for provider, tokens in self.tokens.items():
                for t in tokens:
                    masked = t.model_dump()
                    masked["key"] = (
                        f"{t.key[:4]}...{t.key[-4:]}" if len(t.key) > 8 else "***"
                    )
                    result.append(masked)
            return result

    async def delete_token(self, token_id: str) -> bool:
        """Remove a token from the pool and DB."""
        with self.lock:
            for provider in self.tokens:
                self.tokens[provider] = [
                    t for t in self.tokens[provider] if t.id != token_id
                ]
        deleted = False
        if self.db is not None:
            res = await self.db.api_tokens.delete_one({"id": token_id})
            deleted = res.deleted_count > 0
        return deleted

    # ------------------------------------------------------------------
    # C3: Health probe
    # ------------------------------------------------------------------

    async def probe_all_tokens(self) -> None:
        """Probe each direct-provider token with a 1-token completion call.

        Unhealthy tokens (auth error, quota exhausted) receive a 10-minute
        cooldown so the pool can route around them automatically.
        Called by the background health-monitor task in main.py.
        """
        from litellm import acompletion

        with self.lock:
            # Snapshot to avoid holding the lock during network I/O
            snapshot = {
                provider: list(tokens)
                for provider, tokens in self.tokens.items()
                if provider in ("gemini", "mistral")  # only direct-provider keys need probing
            }

        for provider, token_list in snapshot.items():
            for token_info in token_list:
                now = time.time()
                if token_info.cooldown_until > now:
                    continue  # already in cooldown, skip

                model_map = {"gemini": "gemini/gemini-1.5-flash", "mistral": "mistral/mistral-small-latest"}
                model = model_map.get(provider)
                if not model:
                    continue

                try:
                    await acompletion(
                        model=model,
                        messages=[{"role": "user", "content": "ping"}],
                        max_tokens=1,
                        timeout=10,
                        api_key=token_info.key,
                    )
                    logger.debug("Health probe OK: provider=%s id=%s", provider, token_info.id)
                except Exception as e:
                    err_str = str(e).lower()
                    is_rate = "429" in err_str or "rate limit" in err_str
                    is_auth = "401" in err_str or "auth" in err_str or "invalid" in err_str
                    is_quota = "402" in err_str or "quota" in err_str or "credit" in err_str

                    if is_rate:
                        cooldown = 60.0
                    elif is_auth or is_quota:
                        cooldown = 600.0  # 10-minute cooldown for persistent failures
                    else:
                        cooldown = 0.0  # transient error — don't penalise

                    if cooldown > 0:
                        with self.lock:
                            for t in self.tokens.get(provider, []):
                                if t.id == token_info.id:
                                    t.cooldown_until = time.time() + cooldown
                                    break
                        logger.warning(
                            "Health probe FAIL: provider=%s id=%s error=%s cooldown=%.0fs",
                            provider,
                            token_info.id,
                            str(e)[:120],
                            cooldown,
                        )
                    else:
                        logger.debug(
                            "Health probe transient error (no cooldown): provider=%s id=%s: %s",
                            provider,
                            token_info.id,
                            str(e)[:120],
                        )


# Global token pool instance, initialized in lifespan
token_pool = TokenPool()
