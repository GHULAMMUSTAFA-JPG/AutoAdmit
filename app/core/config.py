"""Environment settings and runtime AdminConfig container."""

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class AppSettings(BaseSettings):
    """Typed environment settings loaded from .env."""
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    MONGODB_URI: str = Field(
        default="mongodb://localhost:27017",
        validation_alias=AliasChoices("MONGO_URI", "MONGODB_URI"),
    )
    DB_NAME: str = Field(default="autoadmit_p12")

    # Primary & Secondary OpenAI-compatible LLM endpoints
    PRIMARY_LLM_BASE_URL: str = Field(default="https://generativelanguage.googleapis.com/v1beta/openai")
    PRIMARY_LLM_API_KEY: str = Field(default="")
    PRIMARY_LLM_MODEL: str = Field(default="gemini-2.0-flash-lite")

    BACKUP_LLM_BASE_URL: str = Field(default="https://coarena.ai/api/v1")
    BACKUP_LLM_API_KEY: str = Field(default="")
    BACKUP_LLM_MODEL: str = Field(default="gemini-3-8-flash")

    # Search-first provider
    SERPER_API_KEY: str = Field(default="")

    # Optional Colab GPU model bridge
    COLAB_BASE_URL: str = Field(default="")
    COLAB_API_KEY: str = Field(default="")

    # Polite crawler settings
    CRAWL_USER_AGENT: str = Field(
        default="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    )
    PER_DOMAIN_DELAY_SEC: float = Field(default=1.15)


settings = AppSettings()
