"""MongoDB database connection manager and schema index setup."""

import asyncio
from typing import Optional, Any
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from pymongo import ASCENDING, IndexModel
from pymongo.errors import ConnectionFailure
from src.config import settings
from src.core.logger import setup_logger

logger = setup_logger("Database")


class DatabaseManager:
    """Manages MongoDB async client lifecycle, collections, and index initialization."""

    def __init__(self, uri: Optional[str] = None, db_name: Optional[str] = None):
        self.uri = uri or settings.MONGODB_URI
        self.db_name = db_name or settings.DB_NAME
        self.client: Optional[AsyncIOMotorClient] = None
        self.db: Optional[AsyncIOMotorDatabase] = None
        self.is_connected: bool = False

    async def connect(self, server_selection_timeout_ms: int = 2000) -> None:
        """Establishes connection to MongoDB and creates unique compound indexes."""
        import socket
        from urllib.parse import urlparse

        # Quick pre-flight check to see if host/port is reachable without stalling Motor worker threads
        parsed = urlparse(self.uri)
        host = parsed.hostname or "127.0.0.1"
        port = parsed.port or 27017
        try:
            sock = socket.create_connection((host, port), timeout=0.3)
            sock.close()
        except Exception as probe_err:
            self.is_connected = False
            self.client = None
            self.db = None
            logger.info(f"MongoDB offline/unreachable at {host}:{port} ({probe_err}). Operating in offline/mock mode.")
            return

        try:
            self.client = AsyncIOMotorClient(
                self.uri,
                serverSelectionTimeoutMS=server_selection_timeout_ms,
                connectTimeoutMS=server_selection_timeout_ms,
                socketTimeoutMS=server_selection_timeout_ms
            )
            self.db = self.client[self.db_name]
            # Ping database to verify connection with strict timeout
            await asyncio.wait_for(
                self.client.admin.command("ping"),
                timeout=server_selection_timeout_ms / 1000.0
            )
            self.is_connected = True
            logger.info(f"Connected to MongoDB at {self.uri} (Database: {self.db_name})")
            await self.create_indexes()
        except (ConnectionFailure, asyncio.TimeoutError, Exception) as exc:
            if self.client:
                self.client.close()
            self.is_connected = False
            self.client = None
            self.db = None
            logger.warning(f"MongoDB connection failed: {exc}. Operating in offline/mock mode.")

    async def create_indexes(self) -> None:
        """Enforces deduplication constraints via compound unique indexes."""
        if self.db is None:
            return

        try:
            # 1. Professors collection deduplication indexes
            professors = self.db["professors"]
            await professors.create_indexes([
                IndexModel([("email", ASCENDING)], unique=True, sparse=True),
                IndexModel([("name", ASCENDING), ("university", ASCENDING)], unique=True),
                IndexModel([("qualification", ASCENDING)]),
                IndexModel([("scraped_at", ASCENDING)])
            ])

            # 2. Outreach drafts indexes
            drafts = self.db["outreach_drafts"]
            await drafts.create_indexes([
                IndexModel([("status", ASCENDING)]),
                IndexModel([("tracking_token", ASCENDING)], unique=True),
                IndexModel([("professor_id", ASCENDING)])
            ])

            # 3. Telemetry and replies indexes
            telemetry = self.db["telemetry"]
            await telemetry.create_indexes([
                IndexModel([("draft_id", ASCENDING)]),
                IndexModel([("tracking_token", ASCENDING)])
            ])

            replies = self.db["inbound_replies"]
            await replies.create_indexes([
                IndexModel([("draft_id", ASCENDING)]),
                IndexModel([("in_reply_to", ASCENDING)])
            ])

            # 4. Universities collection indexes
            universities = self.db["universities"]
            await universities.create_indexes([
                IndexModel([("domain", ASCENDING)], unique=True),
                IndexModel([("region", ASCENDING)]),
                IndexModel([("tier", ASCENDING)]),
                IndexModel([("is_seed", ASCENDING)])
            ])

            # 5. Entity-level University Departments Cache collection indexes
            uni_depts = self.db["university_departments"]
            await uni_depts.create_indexes([
                IndexModel([("domain", ASCENDING), ("discipline_key", ASCENDING)], unique=True),
                IndexModel([("status", ASCENDING)]),
                IndexModel([("expires_at", ASCENDING)]),
                IndexModel([("last_error_code", ASCENDING)])
            ])

            # 6. Phase 1 Async Discovery Jobs collection indexes
            phase1_jobs = self.db["phase1_jobs"]
            await phase1_jobs.create_indexes([
                IndexModel([("job_id", ASCENDING)], unique=True),
                IndexModel([("status", ASCENDING)]),
                IndexModel([("started_at", ASCENDING)])
            ])

            logger.info("MongoDB deduplication and operational indexes successfully verified.")
        except Exception as e:
            logger.error(f"Error creating MongoDB indexes: {e}")

    async def close(self) -> None:
        """Gracefully close database client."""
        if self.client:
            self.client.close()
            self.client = None
            self.db = None
            self.is_connected = False
            logger.info("MongoDB connection closed.")

    def get_collection(self, collection_name: str) -> Any:
        """Returns collection handle or raises if not initialized."""
        if self.db is None or not self.is_connected:
            raise RuntimeError("Database is not connected.")
        return self.db[collection_name]


# Global database manager instance
db_manager = DatabaseManager()

