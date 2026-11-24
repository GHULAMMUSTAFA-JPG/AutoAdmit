"""Motor async MongoDB connection pool and permanent (NO-TTL) index manager."""

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from pymongo import ASCENDING, IndexModel

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger("db.mongo")


class MongoManager:
    """Manages a single Motor client with connection pooling and permanent indexes."""

    def __init__(self, uri: str | None = None, db_name: str | None = None) -> None:
        self.uri = uri or settings.MONGODB_URI
        self.db_name = db_name or settings.DB_NAME
        self.client: AsyncIOMotorClient | None = None
        self.db: AsyncIOMotorDatabase | None = None

    async def connect(self) -> AsyncIOMotorDatabase:
        """Initializes Motor pool (maxPoolSize=50) and guarantees permanent indexes."""
        if self.client is None:
            self.client = AsyncIOMotorClient(
                self.uri,
                maxPoolSize=50,
                serverSelectionTimeoutMS=5000,
            )
            self.db = self.client[self.db_name]
            await ensure_permanent_indexes(self.db)
            logger.info("mongo_connected", db_name=self.db_name)
        assert self.db is not None
        return self.db

    async def close(self) -> None:
        if self.client is not None:
            self.client.close()
            self.client = None
            self.db = None


async def ensure_permanent_indexes(db: AsyncIOMotorDatabase) -> None:
    """Creates permanent unique indexes across all collections. Strictly NO TTL indexes."""
    await db["universities_seed"].create_indexes([
        IndexModel([("domain", ASCENDING)], unique=True, name="uniq_seed_domain"),
        IndexModel([("country", ASCENDING), ("region", ASCENDING), ("rank", ASCENDING)], name="idx_seed_filter"),
    ])

    await db["university_departments"].create_indexes([
        IndexModel(
            [("domain", ASCENDING), ("department", ASCENDING), ("degree", ASCENDING)],
            unique=True,
            name="uniq_dept_domain_dept_degree",
        ),
    ])

    await db["page_snapshots"].create_indexes([
        IndexModel([("url", ASCENDING)], unique=True, name="uniq_snapshot_url"),
        IndexModel([("domain", ASCENDING)], name="idx_snapshot_domain"),
    ])

    await db["professors"].create_indexes([
        IndexModel([("canonical_profile_url", ASCENDING)], unique=True, name="uniq_prof_canonical_url"),
        IndexModel([("university_domain", ASCENDING), ("department", ASCENDING)], name="idx_prof_uni_dept"),
        IndexModel([("source_roster_url", ASCENDING)], name="idx_prof_roster"),
    ])

    await db["jobs"].create_indexes([
        IndexModel([("job_id", ASCENDING)], unique=True, name="uniq_job_id"),
    ])

    await db["needs_review"].create_indexes([
        IndexModel([("domain", ASCENDING), ("stage", ASCENDING)], name="idx_review_domain_stage"),
    ])

    await db["university_site_trees"].create_indexes([
        IndexModel([("domain", ASCENDING)], unique=True, name="uniq_site_tree_domain"),
    ])
    logger.info("permanent_indexes_verified")


mongo_manager = MongoManager()
