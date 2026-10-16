import os
from pathlib import Path
from typing import Literal, Optional
from dotenv import load_dotenv
from pydantic import BaseModel

_PROJECT_ROOT = Path(__file__).resolve().parent.parent

class BackendSettings(BaseModel):
    MONGO_URI: str = "mongodb://localhost:27017"
    MONGO_DB_NAME: str = "ml_intern"
    JWT_SECRET_KEY: str = "dev-secret-key-replace-in-production"
    DEV_MODE: bool = False
    PORT: int = 7860
    TOKEN_HEALTH_INTERVAL_S: int = 600
    LOG_LEVEL: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    SPACE_ID: Optional[str] = None
    
    # Provider keys
    GEMINI_API_KEY: Optional[str] = None
    MISTRAL_API_KEY: Optional[str] = None

_settings_cache: Optional[BackendSettings] = None

def get_settings() -> BackendSettings:
    global _settings_cache
    if _settings_cache is None:
        # Load .env exactly once for the backend process
        load_dotenv(_PROJECT_ROOT / ".env")
        
        env_dict = {
            "MONGO_URI": os.environ.get("MONGO_URI"),
            "MONGO_DB_NAME": os.environ.get("MONGO_DB_NAME"),
            "JWT_SECRET_KEY": os.environ.get("JWT_SECRET_KEY"),
            "DEV_MODE": os.environ.get("DEV_MODE", "false"),
            "PORT": os.environ.get("PORT", "7860"),
            "TOKEN_HEALTH_INTERVAL_S": os.environ.get("TOKEN_HEALTH_INTERVAL_S", "600"),
            "LOG_LEVEL": os.environ.get("LOG_LEVEL", "INFO").upper(),
            "SPACE_ID": os.environ.get("SPACE_ID"),
            "GEMINI_API_KEY": os.environ.get("GEMINI_API_KEY"),
            "MISTRAL_API_KEY": os.environ.get("MISTRAL_API_KEY"),
        }
        # Strip None values so Pydantic defaults apply
        clean_env = {k: v for k, v in env_dict.items() if v is not None}
        
        _settings_cache = BackendSettings.model_validate(clean_env)
    return _settings_cache
