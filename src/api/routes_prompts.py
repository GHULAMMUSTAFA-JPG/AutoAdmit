"""API Endpoints for Dynamic Prompt Management, UI Configuration, and MongoDB Persistence."""

from datetime import datetime, timezone
from typing import List
from fastapi import APIRouter, Depends, HTTPException, status

from src.api.deps import get_current_user
from src.core.database import db_manager
from src.core.logger import setup_logger
from src.models.prompt import PromptRecord, PromptUpdateRequest

router = APIRouter(prefix="/api/v1/prompts", tags=["Prompts"])
logger = setup_logger("PromptService")

# In-memory cache fallback if MongoDB is offline
prompts_cache: dict[str, PromptRecord] = {}

DEFAULT_PROMPTS = [
    PromptRecord(
        id="outreach-synthesis-v1",
        title="Faculty Outreach Cold Email Synthesizer",
        stage="outreach_synthesis",
        system_prompt=(
            "You are an academic liaison crafting concise, highly targeted cold outreach emails "
            "from an aspiring Master's student to Chinese university professors and Master's supervisors (硕导). "
            "STRICT RULES: Keep body under 200 words. Never mention GPA. Focus on specific lab publications and technical overlap. "
            "Highlight self-sufficiency via national scholarships (CSC Type B / Presidential / ANSO)."
        ),
        template_text=(
            "Target Professor: {{professor_name}}\n"
            "University: {{university}}\n"
            "Department: {{department}}\n"
            "Research Topics: {{research_areas}}\n"
            "Lab Digest: {{research_digest}}\n\n"
            "Draft a professional, personalized email (<200 words) proposing Master's research collaboration."
        ),
        variables=["professor_name", "university", "department", "research_areas", "research_digest"],
        is_active=True,
        version=1
    ),
    PromptRecord(
        id="faculty-digest-v1",
        title="Professor Lab Research Digest Generator",
        stage="research_digest",
        system_prompt=(
            "You are an expert scientific literature analyst. Given raw scraped text from a Chinese university faculty bio, "
            "extract the professor's core research directions, recent publications, and primary project themes in 3-4 bullet points."
        ),
        template_text=(
            "Raw Faculty Profile Content:\n{{raw_bio_text}}\n\n"
            "Extract: 1) Active Research Focus, 2) Key Algorithms/Methodologies, 3) 2-3 Recent Paper Themes."
        ),
        variables=["raw_bio_text"],
        is_active=True,
        version=1
    )
]

for p in DEFAULT_PROMPTS:
    prompts_cache[p.id] = p


@router.get("", response_model=List[PromptRecord])
async def list_prompts(user: str = Depends(get_current_user)):
    """Lists all configured system prompts and templates from MongoDB."""
    if db_manager.is_connected and db_manager.db is not None:
        cursor = db_manager.get_collection("prompts").find({})
        results = []
        async for doc in cursor:
            doc.pop("_id", None)
            results.append(PromptRecord(**doc))
        if results:
            return results

        # Initialize defaults if collection is empty
        for dp in DEFAULT_PROMPTS:
            await db_manager.get_collection("prompts").update_one(
                {"id": dp.id},
                {"$set": dp.model_dump()},
                upsert=True
            )
        return DEFAULT_PROMPTS

    return list(prompts_cache.values())


@router.post("", response_model=PromptRecord, status_code=status.HTTP_201_CREATED)
async def create_prompt(prompt: PromptRecord, user: str = Depends(get_current_user)):
    """Creates a new prompt template and saves it to MongoDB."""
    prompt.created_at = datetime.now(timezone.utc)
    prompt.updated_at = datetime.now(timezone.utc)
    prompts_cache[prompt.id] = prompt

    if db_manager.is_connected and db_manager.db is not None:
        await db_manager.get_collection("prompts").update_one(
            {"id": prompt.id},
            {"$set": prompt.model_dump()},
            upsert=True
        )

    logger.info(f"Created new prompt record '{prompt.id}' ({prompt.title})")
    return prompt


@router.put("/{prompt_id}", response_model=PromptRecord)
async def update_prompt(prompt_id: str, update: PromptUpdateRequest, user: str = Depends(get_current_user)):
    """Updates an existing prompt record from the UI and increments version."""
    existing = prompts_cache.get(prompt_id)

    if db_manager.is_connected and db_manager.db is not None:
        doc = await db_manager.get_collection("prompts").find_one({"id": prompt_id})
        if doc:
            doc.pop("_id", None)
            existing = PromptRecord(**doc)

    if not existing:
        raise HTTPException(status_code=404, detail="Prompt record not found")

    if update.title is not None:
        existing.title = update.title
    if update.system_prompt is not None:
        existing.system_prompt = update.system_prompt
    if update.template_text is not None:
        existing.template_text = update.template_text
    if update.variables is not None:
        existing.variables = update.variables
    if update.is_active is not None:
        existing.is_active = update.is_active

    existing.version += 1
    existing.updated_at = datetime.now(timezone.utc)
    prompts_cache[existing.id] = existing

    if db_manager.is_connected and db_manager.db is not None:
        await db_manager.get_collection("prompts").update_one(
            {"id": existing.id},
            {"$set": existing.model_dump()}
        )

    logger.info(f"Updated prompt '{existing.id}' to v{existing.version}")
    return existing


@router.post("/{prompt_id}/activate", response_model=PromptRecord)
async def activate_prompt(prompt_id: str, user: str = Depends(get_current_user)):
    """Activates a prompt and deactivates other prompts in the same stage."""
    target = prompts_cache.get(prompt_id)
    if db_manager.is_connected and db_manager.db is not None:
        doc = await db_manager.get_collection("prompts").find_one({"id": prompt_id})
        if doc:
            doc.pop("_id", None)
            target = PromptRecord(**doc)

    if not target:
        raise HTTPException(status_code=404, detail="Prompt not found")

    target.is_active = True
    target.updated_at = datetime.now(timezone.utc)

    # Deactivate others in same stage
    for p in prompts_cache.values():
        if p.stage == target.stage and p.id != target.id:
            p.is_active = False

    if db_manager.is_connected and db_manager.db is not None:
        await db_manager.get_collection("prompts").update_many(
            {"stage": target.stage},
            {"$set": {"is_active": False}}
        )
        await db_manager.get_collection("prompts").update_one(
            {"id": target.id},
            {"$set": {"is_active": True, "updated_at": target.updated_at}}
        )

    logger.info(f"Activated prompt '{target.id}' for stage '{target.stage}'")
    return target


from pydantic import BaseModel
from typing import Optional
from fastapi import UploadFile, File

class ApplicantProfile(BaseModel):
    name: str = "Applicant"
    cgpa: float = 2.68
    degree: str = "B.S. in Computer Science"
    research_interests: List[str] = ["Computer Vision", "Deep Learning", "Applied AI"]
    key_projects: List[str] = ["PyTorch Model Optimization", "Vision Transformer Pipeline"]
    publications: List[str] = []
    cv_raw_text: Optional[str] = None
    cv_filename: Optional[str] = None
    updated_at: Optional[datetime] = None

# Default in-memory profile
active_applicant_profile = ApplicantProfile(
    name="Prospective Scholar",
    cgpa=2.68,
    degree="B.S. in Computer Science",
    research_interests=["Computer Vision", "Deep Learning", "Vision-Language Models", "Robotics"],
    key_projects=["Real-time Object Detection with PyTorch", "Lightweight Edge AI Inference Engine"],
    publications=["Applied Deep Learning for Embedded Vision (Under Review)"],
    cv_raw_text="Experienced in PyTorch, Python, computer vision architectures, and autonomous AI systems."
)

@router.get("/applicant-profile", response_model=ApplicantProfile)
async def get_applicant_profile_endpoint(user: str = Depends(get_current_user)):
    """Returns stored Applicant CV & Profile Context from MongoDB or active memory."""
    if db_manager.is_connected and db_manager.db is not None:
        try:
            doc = await db_manager.get_collection("applicant_profile").find_one({"id": "primary_profile"})
            if doc:
                doc.pop("_id", None)
                doc.pop("id", None)
                return ApplicantProfile(**doc)
        except Exception:
            pass
    return active_applicant_profile


@router.post("/applicant-profile", response_model=ApplicantProfile)
async def save_applicant_profile_endpoint(
    profile: ApplicantProfile,
    user: str = Depends(get_current_user)
):
    """Saves updated Applicant CV & Profile Context into MongoDB."""
    global active_applicant_profile
    profile.updated_at = datetime.now(timezone.utc)
    active_applicant_profile = profile

    if db_manager.is_connected and db_manager.db is not None:
        try:
            doc = profile.model_dump()
            doc["id"] = "primary_profile"
            await db_manager.get_collection("applicant_profile").update_one(
                {"id": "primary_profile"},
                {"$set": doc},
                upsert=True
            )
        except Exception as err:
            logger.error(f"Failed to persist applicant profile: {err}")

    logger.info(f"Applicant profile saved successfully ({profile.name}, {len(profile.key_projects)} projects).")
    return profile


@router.post("/upload-cv", response_model=ApplicantProfile)
async def upload_applicant_cv_endpoint(
    file: UploadFile = File(...),
    user: str = Depends(get_current_user)
):
    """Uploads applicant CV (.pdf, .txt, .md), extracts text via PyMuPDF/UTF-8, and updates profile context."""
    global active_applicant_profile
    filename = file.filename or "cv_document"
    contents = await file.read()
    raw_text = ""

    if filename.lower().endswith(".pdf"):
        try:
            import fitz
            doc = fitz.open(stream=contents, filetype="pdf")
            extracted = []
            for page in doc:
                extracted.append(page.get_text())
            raw_text = "\n".join(extracted).strip()
        except Exception as e:
            raw_text = f"PDF text extraction note: {e}"
    else:
        try:
            raw_text = contents.decode("utf-8", errors="replace").strip()
        except Exception:
            raw_text = str(contents)[:2000]

    active_applicant_profile.cv_raw_text = raw_text
    active_applicant_profile.cv_filename = filename
    active_applicant_profile.updated_at = datetime.now(timezone.utc)

    # Save to disk as durable local backup
    try:
        from pathlib import Path
        save_dir = Path("data/uploads")
        save_dir.mkdir(parents=True, exist_ok=True)
        save_path = save_dir / filename
        with open(save_path, "wb") as f:
            f.write(contents)
    except Exception:
        pass

    if db_manager.is_connected and db_manager.db is not None:
        try:
            doc = active_applicant_profile.model_dump()
            doc["id"] = "primary_profile"
            await db_manager.get_collection("applicant_profile").update_one(
                {"id": "primary_profile"},
                {"$set": doc},
                upsert=True
            )
        except Exception as err:
            logger.error(f"Failed to persist uploaded CV profile: {err}")

    logger.info(f"Uploaded CV '{filename}' parsed ({len(raw_text)} chars).")
    return active_applicant_profile

