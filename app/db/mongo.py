"""Motor async MongoDB connection pool and permanent (NO-TTL) index manager."""

import asyncio
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from pymongo import ASCENDING, IndexModel
from pymongo.errors import AutoReconnect, ServerSelectionTimeoutError

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
                serverSelectionTimeoutMS=10000,
            )
            self.db = self.client[self.db_name]
            for attempt in range(3):
                try:
                    await ensure_permanent_indexes(self.db)
                    break
                except (AutoReconnect, ServerSelectionTimeoutError):
                    if attempt == 2:
                        raise
                    await asyncio.sleep(1.0)
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

    await db["api_call_traces"].create_indexes([
        IndexModel([("trace_id", ASCENDING)], unique=True, name="uniq_api_trace_id"),
        IndexModel([("job_id", ASCENDING), ("provider", ASCENDING), ("created_at", ASCENDING)], name="idx_trace_job_provider"),
        IndexModel([("status", ASCENDING), ("created_at", ASCENDING)], name="idx_trace_status"),
    ])

    await db["benchmark_runs"].create_indexes([
        IndexModel([("run_id", ASCENDING)], unique=True, name="uniq_benchmark_run_id"),
        IndexModel([("created_at", ASCENDING)], name="idx_benchmark_created"),
    ])

    await db["http_fetch_traces"].create_indexes([
        IndexModel([("trace_id", ASCENDING)], unique=True, name="uniq_http_fetch_trace_id"),
        IndexModel([("job_id", ASCENDING), ("domain", ASCENDING)], name="idx_http_fetch_job_dom"),
    ])

    await db["phase2_link_audits"].create_indexes([
        IndexModel([("audit_id", ASCENDING)], unique=True, name="uniq_link_audit_id"),
        IndexModel([("job_id", ASCENDING), ("domain", ASCENDING)], name="idx_link_audit_job_dom"),
    ])

    await db["system_state"].create_indexes([
        IndexModel([("key", ASCENDING)], unique=True, name="uniq_system_state_key"),
    ])

    await db["domain_playbooks"].create_indexes([
        IndexModel([("domain", ASCENDING)], unique=True, name="uniq_playbook_domain"),
        IndexModel([("cms_fingerprint", ASCENDING)], name="idx_playbook_cms"),
    ])

    await db["prompt_versions"].create_indexes([
        IndexModel([("version_id", ASCENDING)], unique=True, name="uniq_prompt_version_id"),
        IndexModel([("prompt_key", ASCENDING), ("version", ASCENDING)], unique=True, name="uniq_prompt_key_ver"),
        IndexModel([("prompt_key", ASCENDING), ("is_active", ASCENDING)], name="idx_prompt_active"),
    ])

    await db["run_archives"].create_indexes([
        IndexModel([("job_id", ASCENDING)], unique=True, name="uniq_run_archive_job_id"),
        IndexModel([("created_at", ASCENDING)], name="idx_run_archive_created"),
    ])
    logger.info("permanent_indexes_verified")


mongo_manager = MongoManager()
