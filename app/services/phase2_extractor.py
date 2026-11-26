"""Phase 2B: Obfuscated email decoding, 4500-char Markdown truncation, NFKC+whitespace-stripped Grounding Gate, faculty-rank/roster-context eligibility, and grounding_audit."""

import json
import re
import unicodedata
from typing import Any, Literal
from urllib.parse import urljoin

from app.core.llm_router import LLMRouter, llm_router
from app.core.logging import get_logger
from app.core.types import ErrorCode, StepResult
from app.db.repositories import Repository
from app.schemas.entities import NeedsReviewDoc, PageSnapshotDoc, ProfessorDoc
from app.schemas.filters import AdminConfig

logger = get_logger("services.phase2_extractor")

MD_IMG_RE = re.compile(r"!\[[^\]]*\]\(([^)\s]+)")
PHOTO_SKIP_PATTERNS = (
    "search", "logo", "banner", "icon", "btn", "login", "default", "avatar_default",
    "qr", "wechat", "weixin", "email", "mail", "arrow", "bg", "footer", "header", ".svg",
)
STRICT_EMAIL_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._%+-]{1,63}@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$")
HEX_HASH_RE = re.compile(r"^[0-9a-f]{32,}$", re.I)

EMAIL_RE = re.compile(
    r"(?:mailto:)?([a-zA-Z0-9][a-zA-Z0-9_.+-]{1,63}(?:\s*(?:\[at\]|\(at\)|\bat\b|#|@)\s*)[a-zA-Z0-9-]+(?:\s*(?:\[dot\]|\(dot\)|\bdot\b|\.)\s*[a-zA-Z0-9-]+)+)",
    re.I,
)
PHD_NEGATION_RE = re.compile(r"(?:非\s*(?:博导|博士生导师)|(?:博导|博士生导师)\s*[:：]\s*(?:否|无|不是))")
MASTERS_NEGATION_RE = re.compile(r"(?:非\s*(?:硕导|硕士生导师)|(?:硕导|硕士生导师)\s*[:：]\s*(?:否|无|不是))")
EXPLICIT_NO_RECRUIT_RE = re.compile(
    r"(?:不再招收|暂停招生|已退休|not\s+recruiting|no\s+longer\s+recruiting|\bemeritus\b|\bretired\b)",
    re.I,
)
FACULTY_RANK_KEYWORDS = (
    "professor", "associate professor", "assistant professor", "researcher",
    "教授", "副教授", "研究员", "副研究员", "讲席教授", "博导", "硕导", "博士生导师", "硕士生导师",
)
VERIFIED_FACULTY_ROSTER_TOKENS = ("szdw", "js", "ds", "teacherlist", "yjsds", "faculty", "people", "ssyjsds", "dsjj", "师资", "导师")
GRAD_ROSTER_HINTS = ("硕士生导师", "博士生导师", "博导", "硕导", "yjsds", "ssyjsds", "sssds", "bsds", "supervisor")


def is_valid_photo_url(url: str) -> bool:
    """Rejects generic UI icons (search.png, logo, btn, default, .svg) and data URIs."""
    raw = (url or "").strip()
    if not raw or raw.startswith("data:"):
        return False
    low = raw.lower()
    if any(skip in low for skip in PHOTO_SKIP_PATTERNS):
        return False
    return True


def is_valid_email(email: str) -> bool:
    """Strict email validator rejecting leading underscores (_t@), >80-char strings, and RSA/hex cipher hashes."""
    e = (email or "").strip().lower()
    if not e or len(e) > 80:
        return False
    if HEX_HASH_RE.match(e.split("@")[0]):
        return False
    return bool(STRICT_EMAIL_RE.match(e))


def extract_photo_url_from_markdown(markdown: str, base_url: str) -> str:
    """Deterministically finds the first plausible portrait/photo URL in Markdown and resolves it to an absolute URL."""
    for m in MD_IMG_RE.finditer(markdown or ""):
        raw = m.group(1).strip().strip("\"'")
        if not is_valid_photo_url(raw):
            continue
        low = raw.lower()
        if low.endswith((".jpg", ".jpeg", ".png", ".webp")) or "/__local/" in low or "/upload" in low or "/photo" in low:
            return urljoin(base_url, raw)
    return ""


def normalize_nfkc(text: str) -> str:
    """Applies NFKC Unicode normalization and collapses whitespace (including full-width/zero-width spaces)."""
    norm = unicodedata.normalize("NFKC", text or "")
    norm = norm.replace("\u3000", " ").replace("\xa0", " ").replace("\u200b", "")
    return re.sub(r"\s+", " ", norm).strip()


def normalize_for_grounding(text: str) -> str:
    """NFKC + strips ALL whitespace including full-width (\u3000), NBSP (\xa0), and zero-width (\u200b) for resilient verbatim matching."""
    norm = unicodedata.normalize("NFKC", text or "")
    norm = norm.replace("\u3000", "").replace("\xa0", "").replace("\u200b", "")
    return re.sub(r"\s+", "", norm)


def smart_truncate_markdown(markdown: str, max_chars: int = 4500) -> str:
    """Truncates Markdown to max_chars while preserving top header + contact/supervisor sections."""
    text = markdown or ""
    if len(text) <= max_chars:
        return text
    head_len = int(max_chars * 0.72)
    tail_len = max_chars - head_len - 24
    return f"{text[:head_len]}\n\n...[truncated]...\n\n{text[-tail_len:]}"


def decode_obfuscated_email(raw: str) -> str:
    """Decodes obfuscated emails like 'shinningliu at 163 dot com' or 'abc#tsinghua.edu.cn' -> standard email."""
    clean = re.sub(r"\s*(?:\[at\]|\(at\)|\bat\b|#)\s*", "@", raw or "", flags=re.I)
    clean = re.sub(r"\s*(?:\[dot\]|\(dot\)|\bdot\b)\s*", ".", clean, flags=re.I)
    clean = re.sub(r"\s+", "", clean).strip().lower()
    if is_valid_email(clean):
        return clean
    return ""


def extract_email_regex(markdown: str) -> tuple[str, Literal["FOUND", "MISSING", "IMAGE_EMBEDDED"]]:
    """Regex pre-check for mailto:/obfuscated emails and [EMAIL_IMAGE_TAG] markers."""
    m = EMAIL_RE.search(markdown or "")
    if m:
        decoded = decode_obfuscated_email(m.group(1))
        if decoded:
            return decoded, "FOUND"
    if "[EMAIL_IMAGE_TAG]" in (markdown or ""):
        return "", "IMAGE_EMBEDDED"
    return "", "MISSING"


def filter_negated_degrees(markdown: str, breadcrumb: str, degrees: list[str]) -> list[str]:
    """Removes PhD or Masters eligibility if explicit negation appears in the profile text."""
    norm = normalize_nfkc(f"{markdown} {breadcrumb}")
    if EXPLICIT_NO_RECRUIT_RE.search(norm):
        return []
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


def _roster_implies_degrees(source_roster_url: str, roster_title: str = "") -> list[str]:
    blob = f"{source_roster_url} {roster_title}".lower()
    inferred: list[str] = []
    if any(k in blob for k in ("硕士生导师", "硕导", "ssyjsds", "sssds", "masters")):
        inferred.append("masters")
    if any(k in blob for k in ("博士生导师", "博导", "bsds", "phd")):
        inferred.append("phd")
    if not inferred and any(k in blob for k in ("yjsds", "supervisor", "导师")):
        inferred.extend(["masters", "phd"])
    return inferred


def _is_verified_faculty_roster(source_roster_url: str, roster_title: str = "") -> bool:
    blob = f"{source_roster_url} {roster_title}".lower()
    return any(tok in blob for tok in VERIFIED_FACULTY_ROSTER_TOKENS)


def _bio_has_faculty_rank(markdown: str, breadcrumb: str = "") -> bool:
    norm_low = normalize_nfkc(f"{markdown} {breadcrumb}").lower()
    return any(rk in norm_low for rk in FACULTY_RANK_KEYWORDS)


def verify_grounding(
    markdown: str,
    breadcrumb: str,
    name_quote: str,
    supervisor_quote: str,
    *,
    source_roster_url: str = "",
    roster_title: str = "",
) -> tuple[bool, str]:
    """NFKC + full-width/zero-width whitespace-stripped Grounding Gate (with resilient roster_context support)."""
    norm_md = normalize_for_grounding(markdown)
    norm_bc = normalize_for_grounding(breadcrumb)
    combined = f"{norm_md}{norm_bc}"

    nq = normalize_for_grounding(name_quote)
    sq = normalize_for_grounding(supervisor_quote)
    if not nq or nq not in norm_md:
        return False, f"name_evidence_quote '{name_quote}' not found verbatim in Markdown."

    # Never search Markdown literally for the sentinel string 'roster_context'
    if (supervisor_quote or "").strip().lower() in ("roster_context", "rostercontext"):
        if _is_verified_faculty_roster(source_roster_url, roster_title) or _bio_has_faculty_rank(markdown, breadcrumb):
            return True, ""
        return False, "supervisor_evidence_quote 'roster_context' requires verified faculty roster or faculty rank in bio."

    if not sq or sq not in combined:
        if _roster_implies_degrees(source_roster_url, roster_title) or _bio_has_faculty_rank(markdown, breadcrumb):
            return True, ""
        return False, f"supervisor_evidence_quote '{supervisor_quote}' not found verbatim in Markdown or breadcrumb."
    return True, ""


verify_professor_grounding = verify_grounding


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
        roster_title: str = "",
    ) -> StepResult:
        """Runs regex pre-check -> LLM JSON extraction -> NFKC Grounding Gate -> MongoDB upsert."""
        if not self.admin.enable_llm_extraction:
            return StepResult.fail(ErrorCode.LLM_ERROR, "LLM extraction is disabled by AdminConfig.")

        regex_email, regex_status = extract_email_regex(snapshot.markdown)
        sent_md = smart_truncate_markdown(snapshot.markdown, max_chars=4500)
        roster_ctx_line = f"Parent Verified Roster: {source_roster_url} ({roster_title})" if (source_roster_url or roster_title) else ""

        sys_msg = (
            "You extract structured university supervisor profiles strictly verbatim from Markdown. "
            "Respond ONLY with valid JSON. Never fabricate quotes or emails."
        )
        prompt = (
            "Extract structured supervisor information STRICTLY verbatim from the Markdown below.\n"
            "Return ONLY valid JSON with keys:\n"
            '{"name": str, "name_en": str, "title": str, "title_en": str, "email": str, '
            '"degree_eligibility": ["masters"|"phd"], "research_interests": [str], '
            '"research_areas_en": [str], "photo_url": str, '
            '"name_evidence_quote": str, "supervisor_evidence_quote": str}\n'
            "Rules:\n"
            "- FIRST copy an actual verbatim academic rank or supervisor phrase from the Markdown or Breadcrumb into supervisor_evidence_quote (e.g. 教授, 副教授, 研究员, 博导, 硕导, 博士生导师, 硕士生导师, Professor, Associate Professor).\n"
            "- ONLY output \"roster_context\" for supervisor_evidence_quote when the individual bio page completely omits repeating rank/supervisor words.\n"
            "- Copy name_evidence_quote VERBATIM from the Markdown.\n"
            "- Provide concise English translations/romanizations for name_en, title_en, and research_areas_en.\n"
            "- If a real portrait photo URL appears in the Markdown (ignore search/logo/icon/banner), put it in photo_url (else empty string).\n"
            "- Do NOT invent emails or quotes, and NEVER output hex cipher strings as emails.\n\n"
            f"{roster_ctx_line}\n"
            f"Breadcrumb: {snapshot.breadcrumb}\n"
            f"Markdown:\n{sent_md}"
        )
        llm_res = await self.router.complete(
            [{"role": "system", "content": sys_msg}, {"role": "user", "content": prompt}],
            json_mode=True,
            stage="phase2_extractor",
            original_markdown_chars=len(snapshot.markdown or ""),
            sent_markdown_chars=len(sent_md),
        )
        if not llm_res.ok:
            return StepResult.fail(llm_res.error_code or ErrorCode.LLM_ERROR, llm_res.detail or "LLM extraction failed")

        raw_llm_output = str(llm_res.data.get("content") or "")
        try:
            m = re.search(r"\{.*\}", raw_llm_output, re.S)
            parsed = json.loads(m.group(0)) if m else {}
        except Exception as exc:
            await self._route_needs_review(
                snapshot,
                ErrorCode.GROUNDING_FAILED,
                f"Invalid JSON from LLM: {type(exc).__name__}: {exc}",
                {},
                raw_llm_output=raw_llm_output,
            )
            return StepResult.fail(ErrorCode.GROUNDING_FAILED, f"Invalid JSON from LLM: {type(exc).__name__}: {exc}")

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
        if raw_photo and is_valid_photo_url(raw_photo):
            photo_url = urljoin(snapshot.url, raw_photo)
        else:
            photo_url = extract_photo_url_from_markdown(snapshot.markdown, snapshot.url)
        if not is_valid_photo_url(photo_url):
            photo_url = ""

        # 1. NFKC + Whitespace-Stripped Grounding Gate (with roster_context support)
        grounded, reason = verify_grounding(
            snapshot.markdown,
            snapshot.breadcrumb,
            name_quote,
            sup_quote,
            source_roster_url=source_roster_url,
            roster_title=roster_title,
        )
        if not grounded or not name:
            detail = reason or "Missing professor name."
            await self._route_needs_review(
                snapshot,
                ErrorCode.GROUNDING_FAILED,
                detail,
                parsed,
                raw_llm_output=raw_llm_output,
                name_quote=name_quote,
                sup_quote=sup_quote,
            )
            return StepResult.fail(ErrorCode.GROUNDING_FAILED, detail)

        # 2. Negation Rejection (ONLY reject on explicit negation; allow faculty rank or verified roster_context when raw=[])
        norm_page = normalize_nfkc(f"{snapshot.markdown} {snapshot.breadcrumb}")
        has_explicit_negation = bool(
            EXPLICIT_NO_RECRUIT_RE.search(norm_page)
            or (PHD_NEGATION_RE.search(norm_page) and MASTERS_NEGATION_RE.search(norm_page))
        )
        valid_degrees = filter_negated_degrees(snapshot.markdown, snapshot.breadcrumb, raw_degrees)

        if not valid_degrees and not has_explicit_negation and not raw_degrees:
            roster_inferred = _roster_implies_degrees(source_roster_url, roster_title)
            title_blob = f"{title} {title_en}".lower()
            has_faculty_rank = any(rk in title_blob for rk in FACULTY_RANK_KEYWORDS)
            if roster_inferred:
                valid_degrees = filter_negated_degrees(snapshot.markdown, snapshot.breadcrumb, roster_inferred)
            elif has_faculty_rank:
                inferred_from_rank = ["masters", "phd"] if any(k in title_blob for k in ("professor", "教授", "研究员")) else ["masters"]
                valid_degrees = filter_negated_degrees(snapshot.markdown, snapshot.breadcrumb, inferred_from_rank)

        if not valid_degrees:
            detail = f"Supervisor eligibility rejected due to explicit negation or empty eligibility (raw={raw_degrees})."
            await self._route_needs_review(
                snapshot,
                ErrorCode.NEGATED_SUPERVISOR,
                detail,
                parsed,
                raw_llm_output=raw_llm_output,
                name_quote=name_quote,
                sup_quote=sup_quote,
            )
            return StepResult.fail(ErrorCode.NEGATED_SUPERVISOR, detail)

        # 3. Email resolution (strict validator rejecting _t@ and RSA/hex hashes; never drop professor if email is missing)
        email = regex_email if is_valid_email(regex_email) else ""
        email_status = "FOUND" if email else (regex_status if regex_status == "IMAGE_EMBEDDED" else "MISSING")
        if not email:
            raw_llm_email = str(parsed.get("email") or "").strip()
            decoded_llm = decode_obfuscated_email(raw_llm_email)
            norm_md_low = normalize_for_grounding(snapshot.markdown).lower()
            if decoded_llm and is_valid_email(decoded_llm):
                local_part, dom_part = decoded_llm.split("@", 1)
                if decoded_llm in norm_md_low or (local_part in norm_md_low and dom_part.split(".")[0] in norm_md_low):
                    email = decoded_llm
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
            supervisor_evidence_quote=sup_quote or "roster_context",
            grounding_status="VERIFIED",
            status="ACTIVE",
        )
        await self.repo.upsert_professor(prof)
        logger.info("professor_upserted", url=prof.canonical_profile_url, name=prof.name, email_status=prof.email_status)
        return StepResult.success(prof)

    async def extract_inline_table_professors(
        self,
        snapshot: PageSnapshotDoc,
        *,
        department: str,
        source_roster_url: str,
        roster_title: str = "",
        chunk_chars: int = 4000,
    ) -> list[ProfessorDoc]:
        """Archetype B: Extracts multiple professors directly from a single-page/inline table roster in bounded chunks."""
        if not self.admin.enable_llm_extraction:
            return []
        md = snapshot.markdown or ""
        if not md.strip():
            return []
        chunks = [md[i : i + chunk_chars] for i in range(0, min(len(md), chunk_chars * 4), chunk_chars)]
        extracted: list[ProfessorDoc] = []
        seen_names: set[str] = set()
        for chunk_idx, chunk in enumerate(chunks):
            sys_msg = (
                "You extract multiple university faculty/supervisor records strictly verbatim from a roster table in Markdown. "
                "Return ONLY valid JSON."
            )
            prompt = (
                "Extract ALL professors/supervisors listed in this inline roster table chunk.\n"
                'Return JSON ONLY: {"professors": [{"name": str, "name_en": str, "title": str, "title_en": str, '
                '"email": str, "degree_eligibility": ["masters"|"phd"], "research_interests": [str], '
                '"name_evidence_quote": str, "supervisor_evidence_quote": str}]}\n'
                f"Parent Verified Roster: {source_roster_url} ({roster_title})\n"
                f"Markdown:\n{chunk}"
            )
            llm_res = await self.router.complete(
                [{"role": "system", "content": sys_msg}, {"role": "user", "content": prompt}],
                json_mode=True,
                max_tokens=900,
                stage="phase2_inline_table",
                original_markdown_chars=len(md),
                sent_markdown_chars=len(chunk),
            )
            if not llm_res.ok:
                continue
            try:
                m = re.search(r"\{.*\}", str(llm_res.data.get("content") or ""), re.S)
                parsed = json.loads(m.group(0)) if m else {}
                items = parsed.get("professors") or []
            except Exception:
                continue
            for item in items:
                if not isinstance(item, dict):
                    continue
                name = str(item.get("name") or "").strip()
                if not name or name in seen_names:
                    continue
                nq = str(item.get("name_evidence_quote") or name).strip()
                sq = str(item.get("supervisor_evidence_quote") or "roster_context").strip()
                ok_g, _ = verify_grounding(chunk, snapshot.breadcrumb, nq, sq, source_roster_url=source_roster_url, roster_title=roster_title)
                if not ok_g:
                    continue
                raw_degs = [str(d) for d in (item.get("degree_eligibility") or [])]
                valid_degs = filter_negated_degrees(chunk, snapshot.breadcrumb, raw_degs) or _roster_implies_degrees(source_roster_url, roster_title) or ["masters"]
                raw_em = decode_obfuscated_email(str(item.get("email") or ""))
                email = raw_em if is_valid_email(raw_em) else ""
                prof = ProfessorDoc(
                    canonical_profile_url=f"{source_roster_url.split('#')[0]}#inline-{chunk_idx}-{name}",
                    university_domain=snapshot.domain,
                    department=department,
                    source_roster_url=source_roster_url,
                    name=name,
                    name_en=str(item.get("name_en") or name).strip(),
                    title=str(item.get("title") or "").strip(),
                    title_en=str(item.get("title_en") or item.get("title") or "").strip(),
                    email=email,
                    email_status="FOUND" if email else "MISSING",
                    degree_eligibility=valid_degs,
                    research_interests=[str(x).strip() for x in (item.get("research_interests") or []) if str(x).strip()][:8],
                    research_areas_en=[str(x).strip() for x in (item.get("research_interests") or []) if str(x).strip()][:8],
                    photo_url="",
                    name_evidence_quote=nq,
                    supervisor_evidence_quote=sq,
                    grounding_status="VERIFIED",
                    status="ACTIVE",
                )
                await self.repo.upsert_professor(prof)
                seen_names.add(name)
                extracted.append(prof)
        return extracted

    async def _route_needs_review(
        self,
        snapshot: PageSnapshotDoc,
        code: ErrorCode,
        detail: str,
        payload: dict,
        *,
        raw_llm_output: str = "",
        name_quote: str = "",
        sup_quote: str = "",
    ) -> None:
        await self.repo.add_needs_review(
            NeedsReviewDoc(
                domain=snapshot.domain,
                url=snapshot.url,
                stage="phase2_extractor",
                error_code=code.value,
                detail=detail,
                payload=payload,
                grounding_audit={
                    "raw_llm_output": (raw_llm_output or "")[:4000],
                    "extracted_quotes": {
                        "name_evidence_quote": name_quote,
                        "supervisor_evidence_quote": sup_quote,
                    },
                    "markdown_excerpt": (snapshot.markdown or "")[:1500],
                },
            )
        )
