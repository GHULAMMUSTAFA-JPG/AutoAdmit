"""Phase 2B: Regex email pre-check, Multi-Key LLM structured JSON extraction, NFKC Grounding Gate, and idempotent upsert."""

import json
import re
import unicodedata
from typing import Literal
from urllib.parse import urljoin

from app.core.llm_router import LLMRouter, llm_router
from app.core.logging import get_logger
from app.core.types import ErrorCode, StepResult
from app.db.repositories import Repository
from app.schemas.entities import NeedsReviewDoc, PageSnapshotDoc, ProfessorDoc
from app.schemas.filters import AdminConfig

logger = get_logger("services.phase2_extractor")

MD_IMG_RE = re.compile(r"!\[[^\]]*\]\(([^)\s]+)")
PHOTO_SKIP_PATTERNS = ("logo", "banner", "icon", "qr", "wechat", "weixin", "email", "mail", "arrow", "bg", "footer", "header")


def extract_photo_url_from_markdown(markdown: str, base_url: str) -> str:
    """Deterministically finds the first plausible portrait/photo URL in Markdown and resolves it to an absolute URL."""
    for m in MD_IMG_RE.finditer(markdown or ""):
        raw = m.group(1).strip().strip("\"'")
        if not raw or raw.startswith("data:"):
            continue
        low = raw.lower()
        if any(skip in low for skip in PHOTO_SKIP_PATTERNS):
            continue
        if low.endswith((".jpg", ".jpeg", ".png", ".webp")) or "/__local/" in low or "/upload" in low or "/photo" in low:
            return urljoin(base_url, raw)
    return ""

EMAIL_RE = re.compile(
    r"(?:mailto:)?([a-zA-Z0-9_.+-]+(?:\s*(?:\[at\]|\(at\)|@)\s*)[a-zA-Z0-9-]+(?:\s*(?:\[dot\]|\(dot\)|\.)\s*[a-zA-Z0-9-]+)+)",
    re.I,
)
PHD_NEGATION_RE = re.compile(r"(?:非\s*(?:博导|博士生导师)|(?:博导|博士生导师)\s*[:：]\s*(?:否|无|不是))")
MASTERS_NEGATION_RE = re.compile(r"(?:非\s*(?:硕导|硕士生导师)|(?:硕导|硕士生导师)\s*[:：]\s*(?:否|无|不是))")


def normalize_nfkc(text: str) -> str:
    """Applies NFKC Unicode normalization and collapses whitespace for reliable verbatim matching."""
    norm = unicodedata.normalize("NFKC", text or "")
    return re.sub(r"\s+", " ", norm).strip()


def extract_email_regex(markdown: str) -> tuple[str, Literal["FOUND", "MISSING", "IMAGE_EMBEDDED"]]:
    """Regex pre-check for mailto:/obfuscated emails and [EMAIL_IMAGE_TAG] markers."""
    m = EMAIL_RE.search(markdown or "")
    if m:
        raw = m.group(1)
        clean = re.sub(r"\s*(?:\[at\]|\(at\))\s*", "@", raw, flags=re.I)
        clean = re.sub(r"\s*(?:\[dot\]|\(dot\))\s*", ".", clean, flags=re.I)
        clean = re.sub(r"\s+", "", clean)
        if "@" in clean and "." in clean.split("@")[-1]:
            return clean.lower(), "FOUND"
    if "[EMAIL_IMAGE_TAG]" in (markdown or ""):
        return "", "IMAGE_EMBEDDED"
    return "", "MISSING"


def filter_negated_degrees(markdown: str, breadcrumb: str, degrees: list[str]) -> list[str]:
    """Removes PhD or Masters eligibility if explicit Chinese negation appears in the profile text."""
    norm = normalize_nfkc(f"{markdown} {breadcrumb}")
    cleaned: list[str] = []
    for d in degrees:
        dl = d.strip().lower()
        if dl == "phd" and PHD_NEGATION_RE.search(norm):
            continue
        if dl in ("masters", "master") and MASTERS_NEGATION_RE.search(norm):
            continue
        if dl in ("phd", "masters") and dl not in cleaned:
            cleaned.append(dl)
    return cleaned


def verify_grounding(
    markdown: str,
    breadcrumb: str,
    name_quote: str,
    supervisor_quote: str,
) -> tuple[bool, str]:
    """NFKC Grounding Gate: verifies both verbatim quotes literally exist in Markdown or breadcrumb."""
    norm_md = normalize_nfkc(markdown)
    norm_bc = normalize_nfkc(breadcrumb)
    combined = f"{norm_md} {norm_bc}".strip()

    nq = normalize_nfkc(name_quote)
    sq = normalize_nfkc(supervisor_quote)
    if not nq or nq not in norm_md:
        return False, f"name_evidence_quote '{name_quote}' not found verbatim in Markdown."
    if not sq or sq not in combined:
        return False, f"supervisor_evidence_quote '{supervisor_quote}' not found verbatim in Markdown or breadcrumb."
    return True, ""


class Phase2ExtractorService:
    """Extracts grounded ProfessorDoc records from PageSnapshotDoc and blocks hallucinations."""

    def __init__(
        self,
        repo: Repository,
        router: LLMRouter | None = None,
        admin: AdminConfig | None = None,
    ) -> None:
        self.repo = repo
        self.router = router or llm_router
        self.admin = admin or AdminConfig()

    async def extract_from_snapshot(
        self,
        snapshot: PageSnapshotDoc,
        *,
        department: str,
        source_roster_url: str,
    ) -> StepResult:
        """Runs regex pre-check -> LLM JSON extraction -> NFKC Grounding Gate -> MongoDB upsert."""
        if not self.admin.enable_llm_extraction:
            return StepResult.fail(ErrorCode.LLM_ERROR, "LLM extraction is disabled by AdminConfig.")

        regex_email, regex_status = extract_email_regex(snapshot.markdown)

        prompt = (
            "Extract structured supervisor information STRICTLY verbatim from the Markdown below.\n"
            "Return ONLY valid JSON with keys:\n"
            '{"name": str, "name_en": str, "title": str, "title_en": str, "email": str, '
            '"degree_eligibility": ["masters"|"phd"], "research_interests": [str], '
            '"research_areas_en": [str], "photo_url": str, '
            '"name_evidence_quote": str, "supervisor_evidence_quote": str}\n'
            "Rules:\n"
            "- Copy name_evidence_quote and supervisor_evidence_quote VERBATIM from the Markdown or Breadcrumb.\n"
            "- Provide concise English translations/romanizations for name_en, title_en, and research_areas_en.\n"
            "- If a portrait/profile image URL appears in the Markdown, put it in photo_url (else empty string).\n"
            "- Do NOT invent emails or quotes.\n\n"
            f"Breadcrumb: {snapshot.breadcrumb}\n"
            f"Markdown:\n{snapshot.markdown[:4000]}"
        )
        llm_res = await self.router.complete(
            [{"role": "user", "content": prompt}],
            json_mode=True,
            stage="phase2_extractor",
        )
        if not llm_res.ok:
            return StepResult.fail(llm_res.error_code or ErrorCode.LLM_ERROR, llm_res.detail or "LLM extraction failed")

        try:
            m = re.search(r"\{.*\}", llm_res.data["content"], re.S)
            parsed = json.loads(m.group(0)) if m else {}
        except Exception as exc:
            await self._route_needs_review(snapshot, ErrorCode.GROUNDING_FAILED, f"Invalid JSON from LLM: {exc}", {})
            return StepResult.fail(ErrorCode.GROUNDING_FAILED, f"Invalid JSON from LLM: {exc}")

        name = str(parsed.get("name") or "").strip()
        name_en = str(parsed.get("name_en") or "").strip() or name
        title = str(parsed.get("title") or "").strip()
        title_en = str(parsed.get("title_en") or "").strip() or title
        name_quote = str(parsed.get("name_evidence_quote") or "").strip()
        sup_quote = str(parsed.get("supervisor_evidence_quote") or "").strip()
        raw_degrees = [str(d) for d in (parsed.get("degree_eligibility") or [])]
        interests = [str(x).strip() for x in (parsed.get("research_interests") or []) if str(x).strip()][:8]
        areas_en = [str(x).strip() for x in (parsed.get("research_areas_en") or []) if str(x).strip()][:8]
        if not areas_en and interests:
            areas_en = list(interests)

        raw_photo = str(parsed.get("photo_url") or "").strip()
        if raw_photo and not raw_photo.startswith("data:"):
            photo_url = urljoin(snapshot.url, raw_photo)
        else:
            photo_url = extract_photo_url_from_markdown(snapshot.markdown, snapshot.url)

        # 1. NFKC Grounding Gate
        grounded, reason = verify_grounding(snapshot.markdown, snapshot.breadcrumb, name_quote, sup_quote)
        if not grounded or not name:
            detail = reason or "Missing professor name."
            await self._route_needs_review(snapshot, ErrorCode.GROUNDING_FAILED, detail, parsed)
            return StepResult.fail(ErrorCode.GROUNDING_FAILED, detail)

        # 2. Negation Rejection
        valid_degrees = filter_negated_degrees(snapshot.markdown, snapshot.breadcrumb, raw_degrees)
        if not valid_degrees:
            detail = f"Supervisor eligibility rejected due to explicit negation or empty eligibility (raw={raw_degrees})."
            await self._route_needs_review(snapshot, ErrorCode.NEGATED_SUPERVISOR, detail, parsed)
            return StepResult.fail(ErrorCode.NEGATED_SUPERVISOR, detail)

        # 3. Email resolution (never drop professor if email is missing)
        email = regex_email
        email_status = regex_status
        if not email:
            llm_email = str(parsed.get("email") or "").strip().lower()
            if llm_email and "@" in llm_email and llm_email in normalize_nfkc(snapshot.markdown).lower():
                email = llm_email
                email_status = "FOUND"

        prof = ProfessorDoc(
            canonical_profile_url=snapshot.url,
            university_domain=snapshot.domain,
            department=department,
            source_roster_url=source_roster_url,
            name=name,
            name_en=name_en,
            title=title,
            title_en=title_en,
            email=email,
            email_status=email_status,
            degree_eligibility=valid_degrees,
            research_interests=interests,
            research_areas_en=areas_en,
            photo_url=photo_url,
            name_evidence_quote=name_quote,
            supervisor_evidence_quote=sup_quote,
            grounding_status="VERIFIED",
            status="ACTIVE",
        )
        await self.repo.upsert_professor(prof)
        logger.info("professor_upserted", url=prof.canonical_profile_url, name=prof.name, email_status=prof.email_status)
        return StepResult.success(prof)

    async def _route_needs_review(
        self,
        snapshot: PageSnapshotDoc,
        code: ErrorCode,
        detail: str,
        payload: dict,
    ) -> None:
        await self.repo.add_needs_review(
            NeedsReviewDoc(
                domain=snapshot.domain,
                url=snapshot.url,
                stage="phase2_extractor",
                error_code=code.value,
                detail=detail,
                payload=payload,
            )
        )
