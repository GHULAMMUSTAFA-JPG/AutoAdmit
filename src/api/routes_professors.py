"""Faculty profiles and scraping harvest endpoints."""

import asyncio
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel

from src.api.deps import get_current_user
from src.api.routes_discovery import active_estimates
from src.core.database import db_manager
from src.core.logger import setup_logger
from src.models.professor import FacultyProfile, SupervisorQualification
from src.services.llm_agent import llm_agent
from src.services.normalizer import normalizer
from src.services.scraper import harvester

router = APIRouter(prefix="/api/v1/professors", tags=["Professors"])
logger = setup_logger("ProfessorsAPI")

# Memory store for active runtime
professors_cache: dict = {}


class HarvestRequest(BaseModel):
    department_urls: List[str]
    university_name: str
    department_name: str = "School of Computer Science"


class UniversityHarvestItem(BaseModel):
    university_name: str
    department_urls: List[str]
    department_name: str = "School of Computer Science"


class BatchHarvestRequest(BaseModel):
    targets: List[UniversityHarvestItem]


@router.get("", response_model=List[FacultyProfile])
async def list_professors(
    university: Optional[str] = Query(None),
    qualification: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    user: str = Depends(get_current_user)
):
    """Lists verified supervisor profiles with optional filters."""
    # Check MongoDB first if connected
    if db_manager.is_connected and db_manager.db is not None:
        query = {}
        if university:
            query["university"] = {"$regex": university, "$options": "i"}
        if qualification:
            query["qualification"] = qualification
        if search:
            query["$or"] = [
                {"name": {"$regex": search, "$options": "i"}},
                {"research_areas": {"$in": [search]}}
            ]
        cursor = db_manager.get_collection("professors").find(query)
        results = []
        async for doc in cursor:
            doc.pop("_id", None)
            results.append(FacultyProfile(**doc))
        return results

    # Fallback to in-memory cache when MongoDB is offline
    results = list(professors_cache.values())
    if university:
        results = [p for p in results if university.lower() in p.university.lower()]
    if qualification:
        results = [p for p in results if p.qualification == qualification]
    if search:
        results = [
            p for p in results
            if search.lower() in p.name.lower() or any(search.lower() in a.lower() for a in p.research_areas)
        ]
    return results


@router.post("/harvest", response_model=List[FacultyProfile])
async def harvest_faculty_pool(
    request: HarvestRequest,
    user: str = Depends(get_current_user)
):
    """
    Executes grounded scraping across official .edu.cn department endpoints.
    Enforces Pre-Run Cost Gate approval before initiating network operations.
    """
    # Verify Pre-Run Cost Gate
    estimate_id = "default_session"
    if estimate_id in active_estimates:
        estimate, _ = active_estimates[estimate_id]
        if not estimate.is_approved:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Pre-Run Cost Gate is LOCKED. You must approve the cost estimate before launching harvesters."
            )

    extracted_profiles: List[FacultyProfile] = []

    for url in request.department_urls:
        try:
            html, final_url = await harvester.fetch_page(url)
            profile = harvester.parse_profile_html(
                html=html,
                source_url=final_url,
                university_name=request.university_name,
                department_name=request.department_name
            )
            if profile:
                # Deduplication key check
                dedup_key = normalizer.generate_dedup_key(profile.email, profile.name, profile.university)
                if dedup_key not in professors_cache:
                    professors_cache[dedup_key] = profile
                    extracted_profiles.append(profile)

                    # Persist to database if available
                    if db_manager.is_connected and db_manager.db is not None:
                        try:
                            await db_manager.get_collection("professors").update_one(
                                {"email": profile.email},
                                {"$set": profile.model_dump()},
                                upsert=True
                            )
                        except Exception as e:
                            logger.error(f"Error persisting profile to MongoDB: {e}")

                    # Trigger LLM synthesis task asynchronously
                    asyncio.create_task(trigger_draft_creation(profile))
        except Exception as e:
            logger.warning(f"Harvest failed on {url}: {e}. Fault isolated, continuing batch.")

    return extracted_profiles


@router.post("/harvest-batch", response_model=List[FacultyProfile])
async def harvest_batch_faculty(
    request: BatchHarvestRequest,
    user: str = Depends(get_current_user)
):
    """
    Spawns concurrent worker tasks across multiple universities to harvest
    qualified Master's supervisors (硕导) from department endpoints.
    """
    estimate_id = "default_session"
    if estimate_id in active_estimates:
        estimate, _ = active_estimates[estimate_id]
        if not estimate.is_approved:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Pre-Run Cost Gate is LOCKED. You must approve the cost estimate before launching harvesters."
            )

    all_extracted: List[FacultyProfile] = []

    async def _harvest_single_univ(target: UniversityHarvestItem) -> List[FacultyProfile]:
        profiles = []
        for url in target.department_urls:
            try:
                html, final_url = await harvester.fetch_page(url)
                profile = harvester.parse_profile_html(
                    html=html,
                    source_url=final_url,
                    university_name=target.university_name,
                    department_name=target.department_name
                )
                if profile:
                    dedup_key = normalizer.generate_dedup_key(profile.email, profile.name, profile.university)
                    if dedup_key not in professors_cache:
                        professors_cache[dedup_key] = profile
                        profiles.append(profile)

                        if db_manager.is_connected and db_manager.db is not None:
                            try:
                                await db_manager.get_collection("professors").update_one(
                                    {"email": profile.email},
                                    {"$set": profile.model_dump()},
                                    upsert=True
                                )
                            except Exception as e:
                                logger.error(f"Error persisting profile to MongoDB: {e}")

                        asyncio.create_task(trigger_draft_creation(profile))
            except Exception as e:
                logger.warning(f"Batch harvest error on {url}: {e}. Fault isolated, continuing.")
        return profiles

    tasks = [_harvest_single_univ(target) for target in request.targets]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    for res in results:
        if isinstance(res, list):
            all_extracted.extend(res)

    return all_extracted


async def trigger_draft_creation(profile: FacultyProfile):
    """Helper to generate draft and save to drafts collection."""
    try:
        from src.api.routes_drafts import drafts_cache
        digest = await llm_agent.generate_research_digest(profile)
        draft = await llm_agent.generate_outreach_draft(profile, digest)
        drafts_cache[draft.id] = draft

        if db_manager.is_connected and db_manager.db is not None:
            await db_manager.get_collection("outreach_drafts").update_one(
                {"id": draft.id},
                {"$set": draft.model_dump()},
                upsert=True
            )
    except Exception as e:
        logger.error(f"Async draft generation error for {profile.name}: {e}")

