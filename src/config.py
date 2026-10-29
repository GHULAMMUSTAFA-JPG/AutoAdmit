"""Application configuration and environmental parameters with safety defaults."""

import os
from pathlib import Path
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    # Core Safety Switches (Triple Outbound Safety Gates)
    SYSTEM_GATE_ACTIVE: bool = Field(
        default=True,
        description="Master Kill-Switch. When True, all outbound SMTP connections are immediately rejected with 403."
    )
    SANDBOX_MODE: bool = Field(
        default=True,
        description="When True, routes all outbound emails exclusively to TEST_RECIPIENT_EMAIL."
    )
    TEST_RECIPIENT_EMAIL: str = Field(
        default="applicant.test@example.com",
        description="Destination email address when SANDBOX_MODE is active."
    )

    # HTTP & WebSocket Authentication
    BASIC_AUTH_USERNAME: str = Field(default="admin")
    BASIC_AUTH_PASSWORD: str = Field(default="autoadmit_secure_pass_2026")
    JWT_SECRET_KEY: str = Field(default="autoadmit-super-secret-key-change-in-production")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(default=1440)  # 24 hours

    # Database & Persistent Volumes
    MONGODB_URI: str = Field(default="mongodb://localhost:27017")
    DB_NAME: str = Field(default="autoadmit")
    DB_STORAGE_PATH: str = Field(default="./data/db")
    LOG_DIR: str = Field(default="./data/logs")

    # Gemini Intelligence Agent
    GEMINI_API_KEY: str = Field(default="")
    GEMINI_MODEL: str = Field(default="gemini-1.5-flash")

    # Outbound SMTP Engine
    SMTP_HOST: str = Field(default="smtp.gmail.com")
    SMTP_PORT: int = Field(default=587)
    SMTP_USERNAME: str = Field(default="")
    SMTP_PASSWORD: str = Field(default="")
    SENDER_NAME: str = Field(default="Applicant")
    SENDER_EMAIL: str = Field(default="")
    CV_PATH: str = Field(default="./data/cv.pdf")

    # CST Operational Sending Window & Rate Limiting
    CST_SEND_START_HOUR: int = Field(default=9)       # 09:00 CST
    CST_SEND_END_HOUR: int = Field(default=16)        # 16:30 CST
    CST_SEND_END_MINUTE: int = Field(default=30)
    MAX_EMAILS_PER_HOUR: int = Field(default=10)
    MAX_EMAILS_PER_DAY: int = Field(default=25)
    JITTER_MIN_SECONDS: int = Field(default=90)
    JITTER_MAX_SECONDS: int = Field(default=240)

    # Inbound IMAP Response Poller
    IMAP_HOST: str = Field(default="imap.gmail.com")
    IMAP_PORT: int = Field(default=993)
    IMAP_USERNAME: str = Field(default="")
    IMAP_PASSWORD: str = Field(default="")
    IMAP_POLL_INTERVAL_MINUTES: int = Field(default=15)

    # Public Tracking & Web Gateway
    TRACKING_BASE_URL: str = Field(default="http://localhost:8000")

    def ensure_storage_paths(self) -> None:
        """Create persistent storage and log directories if they do not exist."""
        Path(self.DB_STORAGE_PATH).mkdir(parents=True, exist_ok=True)
        Path(self.LOG_DIR).mkdir(parents=True, exist_ok=True)


# Global singleton settings instance
settings = Settings()
settings.ensure_storage_paths()

