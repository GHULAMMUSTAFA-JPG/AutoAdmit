"""Centralized default Qwen prompt templates & safe placeholder renderer for Prompt Studio."""

from typing import Any


class _SafeFormatDict(dict):
    def __missing__(self, key: str) -> str:
        return "{" + key + "}"


DEFAULT_PROMPTS: dict[str, dict[str, str]] = {
    "phase2_extractor": {
        "label": "Phase 2B — Professor Profile Extractor",
        "placeholders": "{roster_ctx_line}, {breadcrumb}, {sent_md}",
        "system_prompt": (
            "You extract structured university supervisor profiles strictly verbatim from Markdown. "
            "Respond ONLY with valid JSON. Never fabricate quotes or emails."
        ),
        "user_prompt_template": (
            "Extract structured supervisor information STRICTLY verbatim from the Markdown below.\n"
            "Return ONLY valid JSON with keys:\n"
            '{{"name": str, "name_en": str, "title": str, "title_en": str, "email": str, '
            '"degree_eligibility": ["masters"|"phd"], "research_interests": [str], '
            '"research_areas_en": [str], "photo_url": str, '
            '"name_evidence_quote": str, "supervisor_evidence_quote": str}}\n'
            "Rules:\n"
            "- FIRST copy an actual verbatim academic rank or supervisor phrase from the Markdown or Breadcrumb into supervisor_evidence_quote (e.g. 教授, 副教授, 研究员, 博导, 硕导, 博士生导师, 硕士生导师, Professor, Associate Professor).\n"
            "- ONLY output \"roster_context\" for supervisor_evidence_quote when the individual bio page completely omits repeating rank/supervisor words.\n"
            "- Copy name_evidence_quote VERBATIM from the Markdown.\n"
            "- Provide concise English translations/romanizations for name_en, title_en, and research_areas_en.\n"
            "- If a real portrait photo URL appears in the Markdown (ignore search/logo/icon/banner), put it in photo_url (else empty string).\n"
            "- Do NOT invent emails or quotes, and NEVER output hex cipher strings as emails.\n\n"
            "{roster_ctx_line}\n"
            "Breadcrumb: {breadcrumb}\n"
            "Markdown:\n{sent_md}"
        ),
    },
    "phase2_inline_table": {
        "label": "Phase 2B — Inline Table Multi-Professor Extractor",
        "placeholders": "{source_roster_url}, {roster_title}, {chunk}",
        "system_prompt": (
            "You extract multiple university faculty/supervisor records strictly verbatim from a roster table in Markdown. "
            "Return ONLY valid JSON."
        ),
        "user_prompt_template": (
            "Extract ALL professors/supervisors listed in this inline roster table chunk.\n"
            'Return JSON ONLY: {{"professors": [{{"name": str, "name_en": str, "title": str, "title_en": str, '
            '"email": str, "degree_eligibility": ["masters"|"phd"], "research_interests": [str], '
            '"name_evidence_quote": str, "supervisor_evidence_quote": str}}]}}\n'
            "Parent Verified Roster: {source_roster_url} ({roster_title})\n"
            "Markdown:\n{chunk}"
        ),
    },
    "tree_branch_select": {
        "label": "Step 1 — Site Tree Branch Selector",
        "placeholders": "{url}, {goal}, {md_links}, {top_k}",
        "system_prompt": (
            "You navigate university websites to locate target department faculty/supervisor rosters. "
            "Respond ONLY with valid JSON using exact candidate URLs provided."
        ),
        "user_prompt_template": (
            "Current page: {url}\nGoal: {goal}\n"
            "Prefer official Chinese department/faculty portals over English brochure subdomains (ev., en.).\n"
            "Ignore News, Admissions, Alumni, Campus Life, Careers, Login.\n\n"
            "Links:\n{md_links}\n\n"
            'Return JSON ONLY: {{"branches": [{{"label": str, "url": str, "zone": "NAV"|"SIDEBAR"|"BODY"}}]}} '
            "(max {top_k} ranked best-first)."
        ),
    },
    "roster_agent_verify": {
        "label": "Step 1 — Agentic Roster Verification Gate",
        "placeholders": "{department}, {degree}, {url}, {page_title}, {breadcrumb}, {top_links}",
        "system_prompt": (
            "You verify whether a webpage is a genuine department faculty/supervisor roster list. "
            "Respond ONLY with valid JSON."
        ),
        "user_prompt_template": (
            "Verify if this webpage is a REAL faculty/supervisor roster list for department '{department}' ({degree}).\n"
            "REJECT university-wide admin/HR pages, news/publications lists, or unrelated departments.\n"
            "URL: {url}\n"
            "Title: {page_title}\n"
            "Breadcrumb: {breadcrumb}\n"
            "Sample Links: {top_links}\n\n"
            'Return JSON ONLY: {{"is_valid_dept_faculty_roster": true|false, "roster_degree_scope": "masters|phd|all|unknown", "reason": str}}'
        ),
    },
}


def render_prompt_template(template: str, **kwargs: Any) -> str:
    """Safely renders `{placeholder}` tokens without crashing on literal JSON braces."""
    try:
        return template.format_map(_SafeFormatDict(kwargs))
    except Exception:
        out = template
        for k, v in kwargs.items():
            out = out.replace("{" + k + "}", str(v))
        return out


async def load_active_prompt_pair(repo: Any, prompt_key: str) -> tuple[str, str]:
    """Loads active (system_prompt, user_prompt_template) from MongoDB `prompt_versions`, falling back to defaults."""
    default = DEFAULT_PROMPTS[prompt_key]
    try:
        if repo is not None:
            doc = await repo.get_active_prompt(prompt_key)
            if doc and doc.user_prompt_template.strip():
                return (doc.system_prompt or default["system_prompt"]), doc.user_prompt_template
    except Exception:
        pass
    return default["system_prompt"], default["user_prompt_template"]
