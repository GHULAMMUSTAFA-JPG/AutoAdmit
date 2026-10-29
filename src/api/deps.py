"""FastAPI dependency injection utilities."""

from typing import Any
from fastapi import Depends
from src.config import Settings, settings
from src.core.database import db_manager
from src.core.security import verify_credentials


def get_settings() -> Settings:
    """Returns application settings."""
    return settings


def get_current_user(user: str = Depends(verify_credentials)) -> str:
    """Enforces authentication check."""
    return user


def get_db() -> Any:
    """Returns database manager instance."""
    return db_manager
