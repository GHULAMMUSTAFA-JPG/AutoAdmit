"""Idempotent async CRUD repositories for permanent MongoDB collections."""

import re
from typing import Any
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.schemas.entities import (
    ApiCallTraceDoc,
    BenchmarkRunDoc,
    DomainPlaybookDoc,
    HttpFetchTraceDoc,
    JobDoc,
    NeedsReviewDoc,
    PageSnapshotDoc,
    Phase2LinkAuditDoc,
    ProfessorDoc,
    PromptVersionDoc,
    RunArchiveDoc,
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

    async def get_professor_by_url(self, canonical_profile_url: str) -> ProfessorDoc | None:
        doc = await self.db["professors"].find_one({"canonical_profile_url": canonical_profile_url})
        if not doc:
            return None
        doc.pop("_id", None)
        return ProfessorDoc(**doc)

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

        def _empty_bucket(p: str) -> dict[str, Any]:
            return {
                "provider": p,
                "total_calls": 0,
                "ok_count": 0,
                "failed_count": 0,
                "avg_latency_ms": 0.0,
                "max_latency_ms": 0,
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0,
                "last_error": None,
                "_lat_sum": 0,
            }

        providers_init = {p: _empty_bucket(p) for p in ("colab_qwen", "deepseek", "gemini", "serper")}
        failure_groups: dict[tuple[str, str, str], dict[str, Any]] = {}
        stage_groups: dict[str, dict[str, Any]] = {}
        time_buckets: dict[str, dict[str, Any]] = {}

        cursor = self.db["api_call_traces"].find(query).sort("created_at", -1)
        async for doc in cursor:
            prov = str(doc.get("provider") or "unknown").lower()
            if prov not in providers_init:
                providers_init[prov] = _empty_bucket(prov)
            bucket = providers_init[prov]
            st = str(doc.get("status") or "ok")
            lat = int(doc.get("latency_ms") or 0)
            err = str(doc.get("error_detail") or "")
            p_tok = int(doc.get("prompt_tokens") or 0)
            c_tok = int(doc.get("completion_tokens") or 0)
            t_tok = int(doc.get("total_tokens") or 0)
            bucket["total_calls"] += 1
            bucket["_lat_sum"] += lat
            bucket["prompt_tokens"] += p_tok
            bucket["completion_tokens"] += c_tok
            bucket["total_tokens"] += t_tok
            if lat > bucket["max_latency_ms"]:
                bucket["max_latency_ms"] = lat

            # Stage aggregation
            stage_key = str(doc.get("stage") or "unknown").strip() or "unknown"
            if stage_key not in stage_groups:
                stage_groups[stage_key] = {
                    "stage": stage_key,
                    "calls": 0,
                    "ok_count": 0,
                    "failed_count": 0,
                    "prompt_tokens": 0,
                    "completion_tokens": 0,
                    "total_tokens": 0,
                    "_lat_sum": 0,
                }
            sg = stage_groups[stage_key]
            sg["calls"] += 1
            sg["prompt_tokens"] += p_tok
            sg["completion_tokens"] += c_tok
            sg["total_tokens"] += t_tok
            sg["_lat_sum"] += lat

            # Hourly timeline aggregation (UTC HH:00)
            ca = doc.get("created_at")
            if hasattr(ca, "strftime"):
                tlabel = ca.strftime("%m-%d %H:00")
            else:
                tlabel = str(ca or "")[:13].replace("T", " ") + ":00"
            if tlabel not in time_buckets:
                time_buckets[tlabel] = {"bucket": tlabel, "calls": 0, "ok_count": 0, "failed_count": 0, "total_tokens": 0}
            tb = time_buckets[tlabel]
            tb["calls"] += 1
            tb["total_tokens"] += t_tok

            if st == "ok":
                bucket["ok_count"] += 1
                sg["ok_count"] += 1
                tb["ok_count"] += 1
            else:
                bucket["failed_count"] += 1
                sg["failed_count"] += 1
                tb["failed_count"] += 1
                if bucket["last_error"] is None:
                    bucket["last_error"] = {"status": st, "http_status": doc.get("http_status"), "detail": err[:240]}
                # Strip dynamic retry timers (e.g. 'in 6s', 'in 12.5s') so identical 429s collapse cleanly
                norm_err = re.sub(r"\bin\s+\d+(?:\.\d+)?\s*s\b", "in <N>s", err, flags=re.I)[:160]
                gk = (prov, st, norm_err)
                if gk not in failure_groups:
                    failure_groups[gk] = {
                        "provider": prov,
                        "status": st,
                        "error_detail": norm_err,
                        "count": 0,
                    }
                failure_groups[gk]["count"] += 1

        providers_out: dict[str, Any] = {}
        for prov, b in providers_init.items():
            total = b["total_calls"]
            b["avg_latency_ms"] = round(b["_lat_sum"] / total, 1) if total else 0.0
            b.pop("_lat_sum", None)
            providers_out[prov] = b

        stages_out: list[dict[str, Any]] = []
        for sg in sorted(stage_groups.values(), key=lambda x: x["calls"], reverse=True):
            c = sg["calls"]
            sg["avg_latency_ms"] = round(sg["_lat_sum"] / c, 1) if c else 0.0
            sg.pop("_lat_sum", None)
            stages_out.append(sg)

        timeline_out = [time_buckets[k] for k in sorted(time_buckets.keys())][-24:]
        failures_sorted = sorted(failure_groups.values(), key=lambda x: x["count"], reverse=True)
        return {
            "job_id": job_id,
            "providers": providers_out,
            "failure_breakdown": failures_sorted,
            "stage_breakdown": stages_out,
            "timeline": timeline_out,
        }

    async def aggregate_domain_tokens(self, domain: str, *, job_id: str | None = None) -> dict[str, int]:
        query: dict[str, Any] = {"domain": domain.lower().strip()}
        if job_id:
            query["job_id"] = job_id.strip()
        stats = {"total_tokens": 0, "qwen_tokens": 0, "deepseek_tokens": 0, "gemini_tokens": 0}
        async for doc in self.db["api_call_traces"].find(query):
            tok = int(doc.get("total_tokens") or 0)
            stats["total_tokens"] += tok
            prov = str(doc.get("provider") or "").lower()
            if prov == "colab_qwen":
                stats["qwen_tokens"] += tok
            elif prov == "deepseek":
                stats["deepseek_tokens"] += tok
            elif prov == "gemini":
                stats["gemini_tokens"] += tok
        return stats

    # ------------------------------------------------------------------ benchmark_runs
    async def insert_benchmark_run(self, run: BenchmarkRunDoc) -> None:
        await self.db["benchmark_runs"].update_one(
            {"run_id": run.run_id},
            {"$set": run.model_dump()},
            upsert=True,
        )

    async def list_benchmark_runs(self, limit: int = 50) -> list[BenchmarkRunDoc]:
        cursor = self.db["benchmark_runs"].find({}).sort("created_at", -1).limit(limit)
        out: list[BenchmarkRunDoc] = []
        async for doc in cursor:
            doc.pop("_id", None)
            out.append(BenchmarkRunDoc(**doc))
        return out

    # ------------------------------------------------------------------ http_fetch_traces & phase2_link_audits
    async def insert_http_fetch_trace(self, trace: HttpFetchTraceDoc) -> None:
        await self.db["http_fetch_traces"].update_one(
            {"trace_id": trace.trace_id},
            {"$set": trace.model_dump()},
            upsert=True,
        )

    async def list_http_fetch_traces(self, *, job_id: str | None = None, domain: str | None = None, limit: int = 500) -> list[HttpFetchTraceDoc]:
        query: dict[str, Any] = {}
        if job_id:
            query["job_id"] = job_id.strip()
        if domain:
            query["domain"] = domain.lower().strip()
        cursor = self.db["http_fetch_traces"].find(query).sort("created_at", -1).limit(limit)
        out: list[HttpFetchTraceDoc] = []
        async for doc in cursor:
            doc.pop("_id", None)
            out.append(HttpFetchTraceDoc(**doc))
        return out

    async def insert_phase2_link_audit(self, audit: Phase2LinkAuditDoc) -> None:
        await self.db["phase2_link_audits"].update_one(
            {"audit_id": audit.audit_id},
            {"$set": audit.model_dump()},
            upsert=True,
        )

    async def list_phase2_link_audits(self, *, job_id: str | None = None, domain: str | None = None, limit: int = 200) -> list[Phase2LinkAuditDoc]:
        query: dict[str, Any] = {}
        if job_id:
            query["job_id"] = job_id.strip()
        if domain:
            query["domain"] = domain.lower().strip()
        cursor = self.db["phase2_link_audits"].find(query).sort("created_at", -1).limit(limit)
        out: list[Phase2LinkAuditDoc] = []
        async for doc in cursor:
            doc.pop("_id", None)
            out.append(Phase2LinkAuditDoc(**doc))
        return out

    # ------------------------------------------------------------------ domain_playbooks (self-learning memory)
    async def upsert_domain_playbook(self, playbook: DomainPlaybookDoc) -> None:
        playbook.domain = playbook.domain.lower().strip()
        playbook.updated_at = utc_now()
        await self.db["domain_playbooks"].update_one(
            {"domain": playbook.domain},
            {"$set": playbook.model_dump()},
            upsert=True,
        )

    async def get_domain_playbook(self, domain: str) -> DomainPlaybookDoc | None:
        doc = await self.db["domain_playbooks"].find_one({"domain": domain.lower().strip()})
        if not doc:
            return None
        doc.pop("_id", None)
        return DomainPlaybookDoc(**doc)

    async def list_domain_playbooks(self, *, cms_fingerprint: str | None = None, limit: int = 200) -> list[DomainPlaybookDoc]:
        query: dict[str, Any] = {}
        if cms_fingerprint:
            query["cms_fingerprint"] = cms_fingerprint
        cursor = self.db["domain_playbooks"].find(query).sort("updated_at", -1).limit(limit)
        out: list[DomainPlaybookDoc] = []
        async for doc in cursor:
            doc.pop("_id", None)
            out.append(DomainPlaybookDoc(**doc))
        return out

    # ------------------------------------------------------------------ prompt_versions (editable Qwen Prompt Studio)
    async def get_active_prompt(self, prompt_key: str) -> PromptVersionDoc | None:
        doc = await self.db["prompt_versions"].find_one({"prompt_key": prompt_key, "is_active": True})
        if not doc:
            return None
        doc.pop("_id", None)
        return PromptVersionDoc(**doc)

    async def list_prompt_versions(self, prompt_key: str | None = None, limit: int = 100) -> list[PromptVersionDoc]:
        query: dict[str, Any] = {"prompt_key": prompt_key} if prompt_key else {}
        cursor = self.db["prompt_versions"].find(query).sort([("prompt_key", 1), ("version", -1)]).limit(limit)
        out: list[PromptVersionDoc] = []
        async for doc in cursor:
            doc.pop("_id", None)
            out.append(PromptVersionDoc(**doc))
        return out

    async def save_prompt_version(
        self,
        *,
        prompt_key: str,
        system_prompt: str,
        user_prompt_template: str,
        note: str = "",
        version_id: str | None = None,
    ) -> PromptVersionDoc:
        import uuid as _uuid
        latest = await self.db["prompt_versions"].find_one({"prompt_key": prompt_key}, sort=[("version", -1)])
        next_ver = int(latest["version"]) + 1 if latest else 1
        await self.db["prompt_versions"].update_many(
            {"prompt_key": prompt_key, "is_active": True},
            {"$set": {"is_active": False}},
        )
        doc = PromptVersionDoc(
            version_id=version_id or f"pv_{_uuid.uuid4().hex[:10]}",
            prompt_key=prompt_key,  # type: ignore[arg-type]
            version=next_ver,
            system_prompt=system_prompt,
            user_prompt_template=user_prompt_template,
            note=note,
            is_active=True,
        )
        await self.db["prompt_versions"].insert_one(doc.model_dump())
        return doc

    async def activate_prompt_version(self, prompt_key: str, version_id: str) -> PromptVersionDoc | None:
        target = await self.db["prompt_versions"].find_one({"prompt_key": prompt_key, "version_id": version_id})
        if not target:
            return None
        await self.db["prompt_versions"].update_many(
            {"prompt_key": prompt_key, "is_active": True},
            {"$set": {"is_active": False}},
        )
        await self.db["prompt_versions"].update_one(
            {"version_id": version_id},
            {"$set": {"is_active": True}},
        )
        target["is_active"] = True
        target.pop("_id", None)
        return PromptVersionDoc(**target)

    # ------------------------------------------------------------------ run_archives & job history
    async def upsert_run_archive(self, archive: RunArchiveDoc) -> None:
        await self.db["run_archives"].update_one(
            {"job_id": archive.job_id},
            {"$set": archive.model_dump()},
            upsert=True,
        )

    async def get_run_archive(self, job_id: str) -> RunArchiveDoc | None:
        doc = await self.db["run_archives"].find_one({"job_id": job_id.strip()})
        if not doc:
            return None
        doc.pop("_id", None)
        return RunArchiveDoc(**doc)

    async def list_recent_jobs(self, limit: int = 30) -> list[JobDoc]:
        cursor = self.db["jobs"].find({}).sort("_id", -1).limit(limit)
        out: list[JobDoc] = []
        async for doc in cursor:
            doc.pop("_id", None)
            out.append(JobDoc(**doc))
        return out

    async def get_active_job(self) -> JobDoc | None:
        doc = await self.db["jobs"].find_one({"status": {"$in": ["RUNNING", "QUEUED"]}}, sort=[("_id", -1)])
        if not doc:
            return None
        doc.pop("_id", None)
        return JobDoc(**doc)

    # ------------------------------------------------------------------ system_state (persisted runtime config)
    async def set_system_state(self, key: str, value: Any) -> None:
        await self.db["system_state"].update_one(
            {"key": key},
            {"$set": {"key": key, "value": value, "updated_at": utc_now()}},
            upsert=True,
        )

    async def get_system_state(self, key: str) -> Any:
        doc = await self.db["system_state"].find_one({"key": key})
        return doc.get("value") if doc else None

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
