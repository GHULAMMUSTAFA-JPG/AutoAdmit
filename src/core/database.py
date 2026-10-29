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
        try:
            self.client = AsyncIOMotorClient(
                self.uri,
                serverSelectionTimeoutMS=server_selection_timeout_ms
            )
            self.db = self.client[self.db_name]
            # Ping database to verify connection
            await self.client.admin.command("ping")
            self.is_connected = True
            logger.info(f"Connected to MongoDB at {self.uri} (Database: {self.db_name})")
            await self.create_indexes()
        except (ConnectionFailure, Exception) as exc:
            self.is_connected = False
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

            logger.info("MongoDB deduplication and operational indexes successfully verified.")
        except Exception as e:
            logger.error(f"Error creating MongoDB indexes: {e}")

    async def close(self) -> None:
        """Gracefully close database client."""
        if self.client:
            self.client.close()
            self.is_connected = False
            logger.info("MongoDB connection closed.")

    def get_collection(self, collection_name: str) -> Any:
        """Returns collection handle or raises if not initialized."""
        if self.db is None:
            raise RuntimeError("Database is not connected.")
        return self.db[collection_name]


# Global database manager instance
db_manager = DatabaseManager()

