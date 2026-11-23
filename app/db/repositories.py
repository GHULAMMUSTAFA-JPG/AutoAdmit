"""Idempotent async CRUD repositories for permanent MongoDB collections."""

from typing import Any
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.schemas.entities import (
    JobDoc,
    NeedsReviewDoc,
    PageSnapshotDoc,
    ProfessorDoc,
    UniversityDeptDoc,
    UniversitySeed,
    utc_now,
)


class Repository:
    """Thin repository layer keeping all MongoDB queries clean and testable."""

    def __init__(self, db: AsyncIOMotorDatabase) -> None:
        self.db = db

    # ------------------------------------------------------------------ universities_seed
    async def upsert_university_seed(self, seed: UniversitySeed) -> None:
        await self.db["universities_seed"].update_one(
            {"domain": seed.domain.lower().strip()},
            {"$set": seed.model_dump()},
            upsert=True,
        )

    async def query_university_seeds(
        self,
        country: str = "China",
        regions: list[str] | None = None,
        limit: int | None = None,
    ) -> list[UniversitySeed]:
        query: dict[str, Any] = {"country": country}
        if regions:
            query["region"] = {"$in": regions}
        cursor = self.db["universities_seed"].find(query).sort("rank", 1)
        if limit is not None:
            cursor = cursor.limit(limit)
        out: list[UniversitySeed] = []
        async for doc in cursor:
            doc.pop("_id", None)
            out.append(UniversitySeed(**doc))
        return out

    # ------------------------------------------------------------------ university_departments
    async def get_department_doc(self, domain: str, department: str, degree: str) -> UniversityDeptDoc | None:
        doc = await self.db["university_departments"].find_one({
            "domain": domain.lower().strip(),
            "department": department.strip(),
            "degree": degree,
        })
        if not doc:
            return None
        doc.pop("_id", None)
        return UniversityDeptDoc(**doc)

    async def upsert_department_doc(self, rec: UniversityDeptDoc) -> None:
        rec.domain = rec.domain.lower().strip()
        rec.department = rec.department.strip()
        rec.updated_at = utc_now()
        await self.db["university_departments"].update_one(
            {"domain": rec.domain, "department": rec.department, "degree": rec.degree},
            {"$set": rec.model_dump()},
            upsert=True,
        )

    # ------------------------------------------------------------------ page_snapshots
    async def get_page_snapshot(self, url: str) -> PageSnapshotDoc | None:
        doc = await self.db["page_snapshots"].find_one({"url": url})
        if not doc:
            return None
        doc.pop("_id", None)
        return PageSnapshotDoc(**doc)

    async def upsert_page_snapshot(self, snap: PageSnapshotDoc) -> None:
        snap.fetched_at = utc_now()
        await self.db["page_snapshots"].update_one(
            {"url": snap.url},
            {"$set": snap.model_dump()},
            upsert=True,
        )

    # ------------------------------------------------------------------ professors
    async def upsert_professor(self, prof: ProfessorDoc) -> None:
        prof.updated_at = utc_now()
        await self.db["professors"].update_one(
            {"canonical_profile_url": prof.canonical_profile_url},
            {"$set": prof.model_dump()},
            upsert=True,
        )

    async def list_professors_by_roster(self, source_roster_url: str) -> list[ProfessorDoc]:
        cursor = self.db["professors"].find({"source_roster_url": source_roster_url})
        out: list[ProfessorDoc] = []
        async for doc in cursor:
            doc.pop("_id", None)
            out.append(ProfessorDoc(**doc))
        return out

    async def list_professors(
        self,
        domains: list[str] | None = None,
        department: str | None = None,
    ) -> list[ProfessorDoc]:
        query: dict[str, Any] = {}
        if domains:
            query["university_domain"] = {"$in": domains}
        if department:
            query["department"] = department
        cursor = self.db["professors"].find(query)
        out: list[ProfessorDoc] = []
        async for doc in cursor:
            doc.pop("_id", None)
            out.append(ProfessorDoc(**doc))
        return out

    async def mark_professor_status(self, canonical_profile_url: str, status_val: str) -> None:
        await self.db["professors"].update_one(
            {"canonical_profile_url": canonical_profile_url},
            {"$set": {"status": status_val, "updated_at": utc_now()}},
        )

    # ------------------------------------------------------------------ jobs & needs_review
    async def upsert_job(self, job: JobDoc) -> None:
        await self.db["jobs"].update_one(
            {"job_id": job.job_id},
            {"$set": job.model_dump()},
            upsert=True,
        )

    async def get_job(self, job_id: str) -> JobDoc | None:
        doc = await self.db["jobs"].find_one({"job_id": job_id})
        if not doc:
            return None
        doc.pop("_id", None)
        return JobDoc(**doc)

    async def add_needs_review(self, item: NeedsReviewDoc) -> None:
        await self.db["needs_review"].insert_one(item.model_dump())

    async def get_system_summary(self) -> dict[str, int]:
        return {
            "universities": await self.db["universities_seed"].count_documents({}),
            "university_departments": await self.db["university_departments"].count_documents({}),
            "page_snapshots": await self.db["page_snapshots"].count_documents({}),
            "professors": await self.db["professors"].count_documents({}),
            "needs_review": await self.db["needs_review"].count_documents({}),
        }
