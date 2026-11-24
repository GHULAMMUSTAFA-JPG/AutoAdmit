"""Idempotent async CRUD repositories for permanent MongoDB collections."""

from typing import Any
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.schemas.entities import (
    ApiCallTraceDoc,
    JobDoc,
    NeedsReviewDoc,
    PageSnapshotDoc,
    ProfessorDoc,
    UniversityDeptDoc,
    UniversitySeed,
    UniversitySiteTreeDoc,
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

    async def list_needs_review(
        self,
        domain: str | None = None,
        stage: str | None = None,
        limit: int = 200,
    ) -> list[NeedsReviewDoc]:
        query: dict[str, Any] = {}
        if domain:
            query["domain"] = domain.lower().strip()
        if stage:
            query["stage"] = stage.strip()
        cursor = self.db["needs_review"].find(query).sort("created_at", -1).limit(limit)
        out: list[NeedsReviewDoc] = []
        async for doc in cursor:
            doc.pop("_id", None)
            out.append(NeedsReviewDoc(**doc))
        return out

    async def list_department_docs(self, domains: list[str] | None = None) -> list[UniversityDeptDoc]:
        query: dict[str, Any] = {}
        if domains:
            query["domain"] = {"$in": domains}
        cursor = self.db["university_departments"].find(query)
        out: list[UniversityDeptDoc] = []
        async for doc in cursor:
            doc.pop("_id", None)
            out.append(UniversityDeptDoc(**doc))
        return out

    # ------------------------------------------------------------------ university_site_trees
    async def get_site_tree(self, domain: str) -> UniversitySiteTreeDoc | None:
        doc = await self.db["university_site_trees"].find_one({"domain": domain.lower().strip()})
        if not doc:
            return None
        doc.pop("_id", None)
        return UniversitySiteTreeDoc(**doc)

    async def upsert_site_tree(self, tree: UniversitySiteTreeDoc) -> None:
        tree.domain = tree.domain.lower().strip()
        tree.updated_at = utc_now()
        await self.db["university_site_trees"].update_one(
            {"domain": tree.domain},
            {"$set": tree.model_dump()},
            upsert=True,
        )

    async def list_site_trees(self, limit: int = 200) -> list[UniversitySiteTreeDoc]:
        cursor = self.db["university_site_trees"].find({}).sort("updated_at", -1).limit(limit)
        out: list[UniversitySiteTreeDoc] = []
        async for doc in cursor:
            doc.pop("_id", None)
            out.append(UniversitySiteTreeDoc(**doc))
        return out

    # ------------------------------------------------------------------ api_call_traces
    async def insert_api_call_trace(self, trace: ApiCallTraceDoc) -> None:
        doc = trace.model_dump()
        doc["request_payload"] = (doc.get("request_payload") or "")[:8000]
        doc["response_payload"] = (doc.get("response_payload") or "")[:8000]
        await self.db["api_call_traces"].update_one(
            {"trace_id": trace.trace_id},
            {"$set": doc},
            upsert=True,
        )

    async def list_api_call_traces(
        self,
        *,
        job_id: str | None = None,
        provider: str | None = None,
        status: str | None = None,
        limit: int = 60,
    ) -> list[ApiCallTraceDoc]:
        query: dict[str, Any] = {}
        if job_id:
            query["job_id"] = job_id.strip()
        if provider:
            query["provider"] = provider.strip().lower()
        if status:
            query["status"] = status.strip()
        cursor = self.db["api_call_traces"].find(query).sort("created_at", -1).limit(limit)
        out: list[ApiCallTraceDoc] = []
        async for doc in cursor:
            doc.pop("_id", None)
            out.append(ApiCallTraceDoc(**doc))
        return out

    async def get_api_call_trace(self, trace_id: str) -> ApiCallTraceDoc | None:
        doc = await self.db["api_call_traces"].find_one({"trace_id": trace_id})
        if not doc:
            return None
        doc.pop("_id", None)
        return ApiCallTraceDoc(**doc)

    async def get_api_analytics_overview(self, *, job_id: str | None = None) -> dict[str, Any]:
        query: dict[str, Any] = {}
        if job_id:
            query["job_id"] = job_id.strip()

        providers_init = {
            p: {
                "provider": p,
                "total_calls": 0,
                "ok_count": 0,
                "failed_count": 0,
                "avg_latency_ms": 0.0,
                "max_latency_ms": 0,
                "last_error": None,
                "_lat_sum": 0,
            }
            for p in ("colab_qwen", "deepseek", "gemini", "serper")
        }
        failure_groups: dict[tuple[str, str, str], dict[str, Any]] = {}

        cursor = self.db["api_call_traces"].find(query).sort("created_at", -1)
        async for doc in cursor:
            prov = str(doc.get("provider") or "unknown").lower()
            if prov not in providers_init:
                providers_init[prov] = {
                    "provider": prov,
                    "total_calls": 0,
                    "ok_count": 0,
                    "failed_count": 0,
                    "avg_latency_ms": 0.0,
                    "max_latency_ms": 0,
                    "last_error": None,
                    "_lat_sum": 0,
                }
            bucket = providers_init[prov]
            st = str(doc.get("status") or "ok")
            lat = int(doc.get("latency_ms") or 0)
            err = str(doc.get("error_detail") or "")
            bucket["total_calls"] += 1
            bucket["_lat_sum"] += lat
            if lat > bucket["max_latency_ms"]:
                bucket["max_latency_ms"] = lat
            if st == "ok":
                bucket["ok_count"] += 1
            else:
                bucket["failed_count"] += 1
                if bucket["last_error"] is None:
                    bucket["last_error"] = {"status": st, "http_status": doc.get("http_status"), "detail": err[:240]}
                gk = (prov, st, err[:160])
                if gk not in failure_groups:
                    failure_groups[gk] = {
                        "provider": prov,
                        "status": st,
                        "error_detail": err[:160],
                        "count": 0,
                    }
                failure_groups[gk]["count"] += 1

        providers_out: dict[str, Any] = {}
        for prov, b in providers_init.items():
            total = b["total_calls"]
            b["avg_latency_ms"] = round(b["_lat_sum"] / total, 1) if total else 0.0
            b.pop("_lat_sum", None)
            providers_out[prov] = b

        failures_sorted = sorted(failure_groups.values(), key=lambda x: x["count"], reverse=True)
        return {
            "job_id": job_id,
            "providers": providers_out,
            "failure_breakdown": failures_sorted,
        }

    async def get_system_summary(self) -> dict[str, int]:
        return {
            "universities": await self.db["universities_seed"].count_documents({}),
            "university_departments": await self.db["university_departments"].count_documents({}),
            "page_snapshots": await self.db["page_snapshots"].count_documents({}),
            "professors": await self.db["professors"].count_documents({}),
            "needs_review": await self.db["needs_review"].count_documents({}),
            "site_trees": await self.db["university_site_trees"].count_documents({}),
            "api_call_traces": await self.db["api_call_traces"].count_documents({}),
        }
